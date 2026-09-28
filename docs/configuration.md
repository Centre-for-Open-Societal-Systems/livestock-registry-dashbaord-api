# Configuration

Never commit real values: `.env` is git-ignored, `.env.example` holds placeholders only, and deployed
environments take values from the platform's secret store.

Settings are read from environment variables, or from a `.env` file in the working directory, by
`app/core/config.py` (pydantic-settings). Complex values are JSON.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DATABASE_URL` | yes | — | PostgreSQL DSN for the livestock registry database, for example `postgresql://dashboard_ro@postgres:5432/livestock_registry`. The service fails to start without it |
| `PGPASSWORD` | recommended | — | Database password, read by asyncpg when the DSN has none. Keeping it out of `DATABASE_URL` avoids URL-encoding it, so a password with `@ : / ? #` just works. A password inside the DSN also works, but must be URL-encoded |
| `DB_POOL_MIN_SIZE` | no | `1` | Connections each worker keeps open |
| `DB_POOL_MAX_SIZE` | no | `5` | Most connections each worker opens under load |
| `API_V1_STR` | no | `/api/v1` | Route prefix for the chart endpoints |
| `ALLOWED_ORIGINS` | no | `["http://localhost:3000"]` | JSON list of origins allowed by CORS. Browsers are not expected to call the API directly, so keep this narrow |
| `PROJECT_NAME` | no | `Livestock Registry Dashboard API` | Title shown in the OpenAPI docs |

Example `.env` for a local livestock registry stack (its Postgres is published on the host):

```ini
DATABASE_URL=postgresql://<user>@host.docker.internal:55432/livestock
PGPASSWORD=<password>
```

## Database account

The service only reads, so give it a dedicated read-only role:

```sql
CREATE ROLE dashboard_ro LOGIN PASSWORD '…';
GRANT CONNECT ON DATABASE livestock_registry TO dashboard_ro;
GRANT USAGE ON SCHEMA public TO dashboard_ro;
GRANT SELECT ON lr_rpt_holding, lr_rpt_animal TO dashboard_ro;
```

This is enough for every endpoint. `GET /health` only needs the ability to connect. The registry's
Helm chart runs the service as the registry's own database user; a dedicated role is the stricter
choice where the platform's database operator allows one.

## Server process

The container runs:

```
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

To change the worker count, override the container command (the registry's Helm chart does, from
`dashboardApi.workers`). Each worker opens its own connection pool of
`DB_POOL_MIN_SIZE`–`DB_POOL_MAX_SIZE` connections (1–5 by default).

## Test settings

| Variable | Default | Description |
| --- | --- | --- |
| `TEST_DATABASE_URL` | none | Server the database tests connect to, with a role that may create schemas. The tests create and drop their own schema and never read registry data. When unset, database tests are skipped and only the unit tests run |
