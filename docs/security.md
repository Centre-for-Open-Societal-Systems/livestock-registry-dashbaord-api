# Security

## Threat model

The service publishes **aggregate statistics** about a register of people. The risks that matter:

1. **SQL injection** through filter parameters.
2. **Unintended exposure**: the API being reachable from outside the platform, or being called by
   anything other than the dashboards BFF.
3. **Re-identification** through very small counts in narrow filter combinations.
4. **Resource exhaustion** of the registry database.

## Controls

### SQL injection

- All user input arrives as query parameters bound to `ChartFilters`, and is turned into SQL in
  exactly one function, `build_where_clause` (`app/api/filters.py`).
- Every value is bound as an asyncpg parameter (`$1…$n`). The only text interpolated into a query is
  literal column names and the generated `WHERE` fragment, which contains no input.
- Fixed predicates are passed to `build_where_clause(extra=…)` as literals, so no code path
  concatenates strings onto a clause.
- Tests assert that injection payloads are bound as values, never appear in the generated SQL, and
  return zero rows.
- Column names, sort orders and similar choices are never taken from input. If they ever need to be,
  map the input through a fixed allow-list.

### Authentication

The only client is the dashboards BFF, a server. It authenticates as itself, never as a user: it
caches chart rows across users and refreshes them in the background, when no user is present.

With authentication on, every chart request needs an OAuth 2.0 access token from the registry's
Keycloak, obtained by the BFF with the **client-credentials grant** for its own client
(`app/core/auth.py`). A token is accepted only when it:

1. names a **trusted issuer** in `iss` (below);
2. is signed by a key that issuer publishes (JWKS), with an asymmetric algorithm. HMAC algorithms
   are refused, so a token "signed" with the public key does not verify;
3. has not expired (`AUTH_LEEWAY_SECONDS` of clock skew are allowed);
4. names this service's Keycloak client, `AUTH_AUDIENCE`, in `aud`;
5. carries the client role `AUTH_ROLE` on that client (`resource_access`).

**Trusted issuers.**

- **`AUTH_IAM_URL`** (the normal case): the registry's IAM, usually its in-namespace Service. Every
  Keycloak realm one of IAM's login providers signs staff in with is trusted. The dashboard gets its
  token from one of those realms too, so no environment URL is configured on either side.
  - The list is read at the first chart request, again every `AUTH_IAM_REFRESH_SECONDS`, and early
    (at most once a minute) when a token names an issuer not on it, so a new provider is followed.
  - IAM's API names a provider's realm only in the authorization URL it returns when a sign-in
    starts, so one sign-in is started per provider. This is exactly what a browser opening the login
    page does, and it leaves only a short-lived transaction in IAM.
  - If IAM cannot be read, the last list is kept. Before any list is known, requests get `503`.
- **`AUTH_ISSUER`**: explicit realm URLs, comma-separated, for a deployment without IAM. Each must
  equal the tokens' `iss` exactly: scheme, host, port and path.

Keys are fetched only from a trusted issuer's JWKS address (`<issuer>/protocol/openid-connect/certs`,
or `AUTH_JWKS_URL` for a single explicit issuer), never from a URL the token supplies. A token naming
any other issuer is refused before any key is fetched.

Access is therefore granted in Keycloak, by giving the role to a caller's service account, and
withdrawn by removing it. A token for any other client of the realm, including a staff user's
token, is refused.

| Answer | When |
| --- | --- |
| `401` with `WWW-Authenticate: Bearer` | No token, or not a bearer token |
| `401` with `error="invalid_token"` | Untrusted issuer, bad signature, unknown key, expired, or wrong audience |
| `403` with `error="insufficient_scope"` | Valid token without `AUTH_ROLE` |
| `503` | The trusted issuers (IAM) or the realm's signing keys cannot be fetched |

Authentication runs before anything else on the chart routes, so a rejected request never reaches
the database. `GET /health` stays open for probes; it reveals only that the service is up.

The signing keys are cached for five minutes. A token with a key id the cache does not hold
triggers one refetch, so Keycloak key rotation needs no restart.

With neither `AUTH_IAM_URL` nor `AUTH_ISSUER` set, authentication is **off** and every request is
accepted. The service logs a
warning at start-up. That is acceptable only while the network alone keeps other clients out.

### Network exposure

- Deploy **without public ingress** whether or not authentication is on: a Kubernetes `ClusterIP`
  Service, a Docker network without a published port, or a port bound to `127.0.0.1` for local use.
- With authentication **off**, that private network is the only control.
- When the BFF runs elsewhere (another cluster or server), turn authentication **on** first, then
  publish the service only on a private route: a VPN, a private load balancer, or the platform's
  internal gateway behind an IP allowlist. Always use TLS on that route, since it carries tokens.
- CORS (`ALLOWED_ORIGINS`) is set narrowly as defence in depth. It is not an access control.

### Data minimisation

- Responses contain only aggregates. No endpoint returns names, identifiers, ear tags, phone
  numbers, addresses or coordinates, and new endpoints must keep to this.
- The reporting views themselves carry no personal data: a keeper appears only as `keeper_key`, a
  one-way hash of the keeper's id, which is enough to count distinct keepers.
- The service reads only the two reporting views. Its database role should be granted `SELECT` on
  those views only (see [Configuration](configuration.md#database-account)).

### Small counts

A count for one kebele, combined with narrow filters, can describe very few keepers. The dashboards
are aggregate-only and not public today. If they are ever published openly, add a minimum cell size
in this service: suppress or round counts below a threshold, for example 5.

### Resource use

- Each request runs one aggregate query on an indexed materialized view.
- Connections are bounded by the pool size per worker.
- The BFF cache means load does not grow with page views.

## Reporting a vulnerability

Report suspected vulnerabilities privately to the repository maintainers rather than in a public
issue.
