# Dashboard API validation

Run `bash ci/run-isolated.sh` on a Docker-capable Linux agent. It owns a unique
PostgreSQL 15 container/network, runs the existing Python 3.11 suites with no
skips allowed, then builds the unchanged root Dockerfile. Existing ASGI auth tests exercise
anonymous/invalid-token denial and authorized database-backed charts; no API
server is started. No host ports are published.
Synthetic test DB objects are removed by exact owner-label checks. Runtime
reporting data and API authentication behavior remain unchanged.

For an already owned test database, install requirements-dev.txt, set
TEST_DATABASE_URL, and run `bash ci/validate.sh`. Never point this variable at an
environment database. Existing fixtures create/drop unique test schemas.
Authentication tests explicitly enable real signature/issuer/audience/role
validation, including a valid service token reaching a database-backed chart.
The fixture's isolated non-auth query mode is not production configuration.

GitHub runs lint, formatting, dependency consistency, syntax, all PostgreSQL
contracts/auth tests, and root Docker build. Actions are immutable SHA pins.
JUnit reports are uploaded even on test failure. No workspace credentials,
image publication, deployment, or external Postman workspace push is needed.
Existing Postman collections remain the reusable external interface contract.

The thin Jenkinsfile loads ci/pipelines/checks.groovy and uses the existing
vpn-agent2 Docker-capable agent pattern. It is validation-only and requests no
credentials. No Jenkins job is created or changed by this repository update.
The owning registry still builds/publishes/deploys its dashboard API at the same
root Dockerfile path. Production acceptance must also verify native reporting
views and authorized calls through the registry-owned BFF/IAM configuration.
