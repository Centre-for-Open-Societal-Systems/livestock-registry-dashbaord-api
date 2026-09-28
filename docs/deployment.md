# Deployment and operations

## Container image

The `Dockerfile` builds a two-stage `python:3.11-slim` image:

1. **Builder:** builds wheels for `requirements.txt`.
2. **Runtime:** installs the wheels, copies `app/`, and runs gunicorn with four Uvicorn workers on
   port `8000`.

The image declares a `HEALTHCHECK` that calls `GET /health` every 30 seconds. `/health` runs
`SELECT 1`, so the container also reports unhealthy when the database is unreachable.

```bash
docker build -t livestock-registry-dashboard-api:<version> .
docker run -d --name livestock-registry-dashboard-api \
  -e DATABASE_URL=postgresql://dashboard_ro@postgres:5432/livestock_registry \
  -e PGPASSWORD=*** \
  -p 127.0.0.1:8006:8000 \
  livestock-registry-dashboard-api:<version>
```

## Docker Compose

`docker-compose.yml` runs the service alone, publishing port `8006` (`API_PORT`) on `127.0.0.1`
only. It requires `DATABASE_URL` from the environment or an uncommitted `.env`, and refuses to start
without it. See [Development](development.md#a-registry-database-to-run-against) for pointing it at a
local registry stack.

## Kubernetes (the registry's Helm chart)

The livestock registry's chart (`helm/openg2p-livestock-registry` in the registry repository)
deploys this service beside the registry, together with the reporting views it reads:

| Values key | Deploys |
| --- | --- |
| `reporting.views.enabled` | A post-install/upgrade hook Job that copies Master Data's geography into `lr_rpt_geo` and applies `reporting_views.sql`, and a CronJob (`reporting.views.refreshSchedule`, every 30 minutes by default) that refreshes the views |
| `dashboardApi.enabled` | The Deployment, a `ClusterIP` Service `<release>-dashboard-api` on port 80, and optionally a VirtualService on a **private** Istio gateway (`dashboardApi.virtualService`) |

The registry's pipeline clones this repository (the branch of the same name, else `develop`), builds
the image beside the registry's own and enables both on its development deploy. The dashboards BFF
then reaches the service at `http://<release>-dashboard-api.<namespace>`.

- **Service:** `ClusterIP` only. Never attach it to a public gateway: the only client is the
  dashboards BFF inside the cluster (see [Security](security.md)).
- **Probes:** readiness on `GET /health`; liveness on the TCP port, so a database outage takes the
  pod out of the Service instead of restarting it.
- **Secrets:** `PGPASSWORD` from the registry's database Secret; `DATABASE_URL` carries no password.
- **Resources:** `100m` / `256Mi` requested per replica. The work is I/O-bound.

## Sizing

- **Connections:** each gunicorn worker holds its own asyncpg pool of `DB_POOL_MIN_SIZE` to
  `DB_POOL_MAX_SIZE` connections (1–5 by default). One replica therefore keeps **workers × 1** open
  and uses at most **workers × 5**. The database is shared with the rest of the registry, so keep
  the pool small. For most deployments one replica with 2 workers is plenty.
- **Load:** the dashboards BFF caches every chart and filter combination, so load does not grow
  with page views.
- **Query cost:** each request is one aggregate over an indexed materialized view.

## Data freshness

A figure in the dashboards can lag the register by at most:

- **the view refresh interval** (30 minutes by default, owned by the livestock registry), plus
- **the BFF cache TTL** (15 minutes by default)

After a bulk import, run the refresh CronJob by hand to publish the new data:

```bash
kubectl -n <namespace> create job --from=cronjob/<release>-lr-reporting-views-refresh lr-refresh-now
```

## Monitoring

| Signal | Where | Healthy |
| --- | --- | --- |
| Container health | Kubernetes probe on `/health` | ready |
| Error rate | gunicorn logs (stdout) | No `500` responses |
| Database connections | `pg_stat_activity` filtered by the service's user | ≤ workers × `DB_POOL_MAX_SIZE` per replica |
| View freshness | `reporting_refresh_latest` in the registry database (written by the refresh job) | Last `refreshed` within the schedule |

gunicorn does not write access logs by default. Add `--access-logfile -` to the command if you need
per-request logs.

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Container restarts, and the log says `DATABASE_URL` is missing | Required setting absent | Set `DATABASE_URL` |
| `/health` returns 500 or the pod is not ready | Database unreachable, wrong credentials, or pool exhausted | Check network and DNS to Postgres, credentials, and `pg_stat_activity` |
| A chart returns 500 with `relation "lr_rpt_holding" does not exist` | The reporting views have not been created in this database | Enable `reporting.views` in the registry's chart, or run its `reporting-views` compose service |
| Geography charts show everything under `Unknown` | `lr_rpt_geo` is empty: the Master Data copy was skipped or failed | Check the reporting job's log for `reporting-geo-sync`, and the `reporting.masterData` values |
| All counts are 0 | Filters match nothing, or the views are empty | Retry without filters, then check `SELECT count(*) FROM lr_rpt_holding` |
| Totals lower than expected | Only `ACTIVE` records are counted by default | Pass `recordState` explicitly, or use `livestockByRecordState` |
| Figures lag the registry | Views not refreshed, or the BFF cache | Check the refresh CronJob. Figures appear after the next refresh plus one cache period |
