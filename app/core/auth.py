"""Service-to-service authentication of chart requests.

The dashboards BFF calls this service with an access token it gets from the
registry's Keycloak with the client-credentials grant, as its own client. A
request is accepted when its `Authorization: Bearer` token:

  1. names a trusted issuer in `iss` (see below);
  2. is signed by a key that issuer publishes (JWKS), with an asymmetric
     algorithm;
  3. is not expired (AUTH_LEEWAY_SECONDS of clock skew allowed);
  4. names AUTH_AUDIENCE, this service's Keycloak client, in `aud`;
  5. carries AUTH_ROLE among that client's roles (`resource_access`).

Trusted issuers come from either or both of:

  - AUTH_IAM_URL: the registry's IAM. Every realm one of its login providers
    signs staff in with is trusted, so nothing environment-specific is
    configured: the dashboard gets its token from one of those realms too.
    The list is read from IAM at start-up, again every
    AUTH_IAM_REFRESH_SECONDS, and early (at most once a minute) when a token
    names an issuer not on it.
  - AUTH_ISSUER: issuer URLs, comma-separated, for a deployment without IAM.

Signing keys are only ever fetched from a trusted issuer's JWKS address,
never from a URL the token supplies.

Keycloak puts a client in `aud` by itself when the token carries one of the
client's roles, so a caller needs no setup beyond that role on its service
account. No user is involved: the BFF caches chart rows across users and
refreshes them in the background, so the caller is always the BFF itself.

Answers follow RFC 6750: 401 with `WWW-Authenticate: Bearer` for a missing or
invalid token, 403 (`insufficient_scope`) for a valid token without the role,
and 503 when the trusted issuers or their signing keys cannot be fetched.

Off while neither AUTH_IAM_URL nor AUTH_ISSUER is set: every request is then
accepted, and the service must stay unreachable from outside its private
network (see docs/security.md).
"""

import asyncio
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import cache
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

log = logging.getLogger(__name__)

# Asymmetric only. With an HMAC algorithm allowed, a token "signed" with the
# public key would verify (algorithm confusion).
ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]

# How long fetched signing keys are trusted. An unknown key id (Keycloak
# rotated its keys) triggers a refetch regardless.
JWKS_CACHE_SECONDS = 300

# A token naming an unknown issuer re-reads IAM's providers at most this often.
IAM_MISS_REFRESH_SECONDS = 60
# While IAM cannot be read and no list is known yet, retry at most this often.
IAM_RETRY_SECONDS = 10

HTTP_TIMEOUT_SECONDS = 10

# Keycloak's authorization endpoint: <base>/realms/<realm>/protocol/openid-connect/auth
KEYCLOAK_AUTHORIZE = re.compile(r"^(?P<realm>.*/realms/[^/]+)/protocol/openid-connect/auth$")


class IssuersUnavailable(Exception):
    """The trusted issuers cannot be determined (IAM unreachable)."""


@dataclass(frozen=True)
class Caller:
    """The authenticated client: Keycloak's `azp` (client id) and `sub`."""

    client_id: str
    subject: str


def keycloak_jwks_url(issuer: str) -> str:
    return f"{issuer}/protocol/openid-connect/certs"


def _normalise(issuer: str) -> str:
    return issuer.strip().rstrip("/")


def _http_json(method: str, url: str) -> Any:
    """One JSON request to IAM (blocking; run in a worker thread)."""
    request = urllib.request.Request(url, method=method, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310 (configured URL)
        return json.loads(response.read() or b"null")


def realm_of(authorization_url: str) -> str | None:
    """The issuer (realm URL) behind a Keycloak authorization URL, or None."""
    parts = urllib.parse.urlsplit(authorization_url)
    match = KEYCLOAK_AUTHORIZE.match(parts.path)
    return f"{parts.scheme}://{parts.netloc}{match['realm']}" if match else None


def discover_iam_issuers(iam_url: str) -> dict[str, str]:
    """Issuer -> JWKS URL for every realm the IAM at `iam_url` signs staff in with.

    IAM's public API names a provider's realm only in the authorization URL it
    hands out when a sign-in starts, so one sign-in is started per provider,
    exactly as a browser opening the login page does. Each creates a
    short-lived transaction in IAM and nothing else.
    """
    base = iam_url.rstrip("/")
    providers = (_http_json("GET", f"{base}/auth/get_login_providers") or {}).get("loginProviders") or []
    issuers: dict[str, str] = {}
    for provider in providers:
        query = urllib.parse.urlencode({"id": provider.get("id"), "redirect_uri": f"{base}/"})
        try:
            started = _http_json("POST", f"{base}/auth/start_authentication_transaction?{query}") or {}
        except Exception as error:  # one broken provider must not hide the others
            log.warning("IAM login provider %s: cannot start a sign-in: %s", provider.get("id"), error)
            continue
        issuer = realm_of(str(started.get("redirectUrl") or ""))
        if issuer:
            issuers[issuer] = keycloak_jwks_url(issuer)
        else:
            log.warning("IAM login provider %s does not lead to a Keycloak realm; skipped", provider.get("id"))
    if not issuers:
        raise IssuersUnavailable(f"no Keycloak realm found behind the login providers of {base}")
    return issuers


class TrustedIssuers:
    """The issuers whose tokens are accepted, each with its JWKS URL."""

    def __init__(self, static: dict[str, str], iam_url: str | None, refresh_seconds: int) -> None:
        self.static = static
        self.iam_url = iam_url
        self.refresh_seconds = refresh_seconds
        self._discovered: dict[str, str] | None = None
        self._read_at = 0.0
        self._failed_at = float("-inf")
        self._lock = asyncio.Lock()

    def describe(self) -> str:
        parts = sorted(self.static)
        if self.iam_url:
            parts.append(f"the realms of IAM {self.iam_url}")
        return ", ".join(parts)

    async def jwks_url(self, issuer: str) -> str | None:
        """The JWKS URL for a trusted issuer; None for an untrusted one."""
        issuer = _normalise(issuer)
        if issuer in self.static:
            return self.static[issuer]
        if not self.iam_url:
            return None
        now = time.monotonic()
        if self._discovered is None:
            if now - self._failed_at > IAM_RETRY_SECONDS:
                await self._refresh()
        elif now - self._read_at > self.refresh_seconds:
            await self._refresh()
        elif issuer not in self._discovered and now - self._read_at > IAM_MISS_REFRESH_SECONDS:
            await self._refresh()
        if self._discovered is None:
            raise IssuersUnavailable("IAM's login providers could not be read")
        return self._discovered.get(issuer)

    async def _refresh(self) -> None:
        async with self._lock:
            # Another request may have refreshed while this one waited.
            if self._discovered is not None and time.monotonic() - self._read_at <= IAM_MISS_REFRESH_SECONDS:
                return
            try:
                found = await run_in_threadpool(discover_iam_issuers, self.iam_url)
            except Exception as error:
                log.error("cannot read the trusted issuers from IAM %s: %s", self.iam_url, error)
                if self._discovered is None:
                    self._failed_at = time.monotonic()
                else:
                    self._read_at = time.monotonic()  # keep the last list until the next interval
                return
            if found != self._discovered:
                log.info("trusted issuers from IAM: %s", ", ".join(sorted(found)))
            self._discovered = found
            self._read_at = time.monotonic()


def _unauthorized(description: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=description,
        headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="{description}"'},
    )


class TokenVerifier:
    def __init__(self, issuers: TrustedIssuers, audience: str, role: str, leeway: int) -> None:
        self.issuers = issuers
        self.audience = audience
        self.role = role
        self.leeway = leeway
        self._jwks: dict[str, jwt.PyJWKClient] = {}

    def _keys(self, jwks_url: str) -> jwt.PyJWKClient:
        client = self._jwks.get(jwks_url)
        if client is None:
            client = jwt.PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=JWKS_CACHE_SECONDS, timeout=5)
            self._jwks[jwks_url] = client
        return client

    def _decode(self, token: str, issuer: str, jwks_url: str) -> dict[str, Any]:
        # Blocking (the key fetch is plain urllib): run in a worker thread.
        key = self._keys(jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            key.key,
            algorithms=ALGORITHMS,
            audience=self.audience,
            issuer=issuer,
            leeway=self.leeway,
            options={"require": ["exp", "iss", "aud"]},
        )

    async def verify(self, token: str) -> Caller:
        # Read `iss` unverified only to pick the trusted issuer's keys; the
        # signature and the issuer are verified below.
        try:
            claimed = jwt.decode(token, options={"verify_signature": False}).get("iss")
        except jwt.InvalidTokenError as error:
            raise _unauthorized("Invalid token") from error
        if not isinstance(claimed, str) or not claimed:
            raise _unauthorized("Invalid token")
        try:
            jwks_url = await self.issuers.jwks_url(claimed)
        except IssuersUnavailable as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Token verification is unavailable") from error
        if jwks_url is None:
            raise _unauthorized("Untrusted issuer")

        try:
            claims = await run_in_threadpool(self._decode, token, claimed, jwks_url)
        except jwt.PyJWKClientConnectionError as error:
            log.error("cannot fetch the signing keys from %s: %s", jwks_url, error)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Token verification is unavailable") from error
        except jwt.PyJWKClientError as error:
            # Typically a key id the realm does not publish.
            raise _unauthorized("Unknown signing key") from error
        except jwt.ExpiredSignatureError as error:
            raise _unauthorized("Token expired") from error
        except jwt.InvalidTokenError as error:
            raise _unauthorized("Invalid token") from error

        roles = ((claims.get("resource_access") or {}).get(self.audience) or {}).get("roles") or []
        caller = Caller(client_id=str(claims.get("azp") or ""), subject=str(claims.get("sub") or ""))
        if self.role not in roles:
            log.warning("client %r lacks role %r on %r", caller.client_id, self.role, self.audience)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {self.role} on {self.audience} required",
                headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
            )
        return caller


@cache
def get_verifier() -> TokenVerifier | None:
    """The verifier for the configured issuers; None while authentication is off."""
    explicit = [_normalise(i) for i in (settings.AUTH_ISSUER or "").split(",") if i.strip()]
    iam_url = (settings.AUTH_IAM_URL or "").strip().rstrip("/") or None
    if not explicit and not iam_url:
        return None
    jwks_override = (settings.AUTH_JWKS_URL or "").strip()
    if jwks_override and len(explicit) != 1:
        raise ValueError("AUTH_JWKS_URL needs exactly one AUTH_ISSUER")
    static = {issuer: jwks_override or keycloak_jwks_url(issuer) for issuer in explicit}
    issuers = TrustedIssuers(static, iam_url, settings.AUTH_IAM_REFRESH_SECONDS)
    return TokenVerifier(issuers, settings.AUTH_AUDIENCE, settings.AUTH_ROLE, settings.AUTH_LEEWAY_SECONDS)


def reset() -> None:
    """Rebuild the verifier from the settings on next use (tests)."""
    get_verifier.cache_clear()


async def require_caller(request: Request) -> Caller | None:
    """FastAPI dependency: the authenticated caller, or None while authentication is off."""
    verifier = get_verifier()
    if verifier is None:
        return None
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await verifier.verify(token.strip())
