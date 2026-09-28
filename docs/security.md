# Security

## Threat model

The service publishes **aggregate statistics** about a register of people. The risks that matter:

1. **SQL injection** through filter parameters.
2. **Unintended exposure**: the API being reachable from outside the platform, or being used to
   enumerate data.
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

### Network exposure and authentication

- The service has **no authentication**, by design. Its only client is the dashboards BFF, a server
  on the same private network.
- It must be deployed **without public ingress**:
  - a Kubernetes `ClusterIP` Service, or
  - a Docker network without a published port, or
  - a port bound to `127.0.0.1` for local use
- CORS (`ALLOWED_ORIGINS`) is set narrowly as defence in depth. It is not an access control.
- If the API ever needs to be reachable beyond the private network, put it behind the platform's
  gateway with service-to-service authentication first.

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
