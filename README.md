# Livestock Registry Dashboard API

The **dashboard service** of the OpenG2P livestock registry: a read-only HTTP service that serves
aggregate statistics about the registry to the OAN dashboards. It exposes one endpoint per dashboard
chart and computes each response from the registry's materialized reporting views
(`lr_rpt_holding`, `lr_rpt_animal`).

Each registry (farmer, livestock, crop sown, …) publishes its statistics through its own dashboard
service, and all of them share one HTTP contract. This service is the only component that holds
credentials for the livestock registry database: the dashboards call the service and never the
database.

- **Stack:** Python 3.11, FastAPI, asyncpg, gunicorn with Uvicorn workers
- **Consumer:** the OAN dashboards backend-for-frontend (BFF), which caches responses
- **Data:** aggregates only. The service never returns names, identifiers, ear tags, contact
  details or coordinates

## Quick start

The reporting views are created by the livestock registry itself (its db-seed image ships
`reporting_views.sql`; its Helm chart and local compose stack apply it). Against a local registry
stack:

```bash
# in the livestock-registry repository: build the lr_rpt_* views
docker compose --env-file local/.env --profile reporting up reporting-views

# here
cp .env.example .env              # point DATABASE_URL at the livestock registry database
docker compose up -d --build      # serves on http://localhost:8006
curl http://localhost:8006/health
curl "http://localhost:8006/api/v1/charts/livestockKpis?region=ET04"
```

Interactive OpenAPI docs are served at `http://localhost:8006/docs`.

A Postman collection with every endpoint is in `postman/`. Each request has contract tests, and the
filters are included but disabled. Import it and set the `baseUrl` variable to the service's address
(default `http://localhost:8006`), or run it from the command line:

```bash
npx newman run "postman/Livestock Registry Dashboard Service.postman_collection.json" \
  --env-var baseUrl=http://localhost:8006
```

## Endpoints at a glance

| Endpoint | Returns |
| --- | --- |
| `GET /health` | Liveness and database connectivity |
| `GET /api/v1/charts/livestockKpis` | Headline totals: holdings, keepers, female keepers, animals, species, breeds |
| `GET /api/v1/charts/livestockBySpecies` | Animals and keepers per species |
| `GET /api/v1/charts/livestockByBreed` | Animals per breed |
| `GET /api/v1/charts/livestockKeepersByRegion` | Keepers and animals per region |
| `GET /api/v1/charts/livestockKeepersByZone`, `…ByWoreda`, `…ByKebele` | The same per zone, woreda and kebele, for map drill-down |
| `GET /api/v1/charts/livestockTopWoredas` | The eight woredas with the most keepers |
| `GET /api/v1/charts/herdHealthSplit` | Animals per health status |
| `GET /api/v1/charts/livestockVaccinationStatus` | Animals per vaccination status |
| `GET /api/v1/charts/livestockBySex` | Animals per sex |
| `GET /api/v1/charts/livestockTrendByMonth` | Holdings, keepers and animals per registration month |
| `GET /api/v1/charts/livestockByState` | Holdings per approval-workflow state |
| `GET /api/v1/charts/livestockByRecordState` | Holdings per record status |

All chart endpoints accept the same filters: `region`, `zone`, `woreda`, `kebele`, `recordState`,
`state` and `species`. See the [API reference](docs/api-reference.md) for the full contract.

## Documentation

| Document | Contents |
| --- | --- |
| [Architecture](docs/architecture.md) | Where the service sits, data flow, data sources, design decisions |
| [API reference](docs/api-reference.md) | Every endpoint, parameter and response field, with examples |
| [Configuration](docs/configuration.md) | Environment variables |
| [Development](docs/development.md) | Local setup, tests, linting, adding an endpoint |
| [Deployment and operations](docs/deployment.md) | Container image, Helm, sizing, health checks, troubleshooting |
| [Security](docs/security.md) | Threat model, SQL-injection controls, network exposure, data protection |
| [AGENTS.md](AGENTS.md) | Rules for contributors and coding agents working in this repository |

## License

See [LICENSE](LICENSE).
