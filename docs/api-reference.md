# API reference

- **Base URL:** `http://<host>:8006` when run with the provided compose file (the container listens
  on `8000`).
- **Route prefix:** `/api/v1` (configurable with `API_V1_STR`).
- **Methods and responses:** every endpoint is `GET` and returns `application/json`.
- **OpenAPI:** the generated schema is at `/openapi.json`, with an interactive UI at `/docs`.

## Authentication

When the service runs with authentication on (`AUTH_IAM_URL` or `AUTH_ISSUER` set), every `/api/v1/charts/*` request needs a bearer token:

```
Authorization: Bearer <access token>
```

The token is a Keycloak client-credentials token whose client holds the role `AUTH_ROLE` (default
`charts:read`) on this service's client `AUTH_AUDIENCE` (default `livestock-registry-dashboard-api`).
`GET /health` needs no token. For example:

```bash
TOKEN=$(curl -s -d grant_type=client_credentials -d client_id=livestock-registry-dashboard \
  -d client_secret="$CLIENT_SECRET" "$ISSUER/protocol/openid-connect/token" | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8005/api/v1/charts/livestockKpis
```

See [Security](security.md#authentication) for what is checked.

## Conventions

### Response shape

Every chart endpoint returns a **JSON array of row objects**. There is no envelope:

- a chart with no matching data returns `[]`
- a single-figure chart (`livestockKpis`) returns an array with one object

Counts are JSON integers. Animal counts are **head counts**: a poultry flock or a set of beehives
recorded as one line with a quantity counts that quantity.

Enumerations are returned as the registry's **codes** (`FEMALE`, `HEALTHY`, `VERIFIED`), and the
client labels them; a missing value is `"UNKNOWN"`. Species and breeds come from the registry's own
lookup table, so they are returned both as a label (`species`, `breed`) and as the lookup key
(`species_code`, `breed_code`).

A geographic unit is returned with its name and its P-code (`region`, `region_code`). A holding
whose unit could not be resolved to a P-code is reported with `<level>_code` `"Unknown"` and its
recorded name, so totals are never silently reduced.

### Response keys are a contract

The key names of each chart are relied on by the dashboards, and the test suite pins them. Renaming
or removing a key is a breaking change. Adding a key is not.

## Common filter parameters

Every chart endpoint accepts these optional query parameters. The value `all` behaves the same as
leaving the parameter out.

| Parameter | Matches | Notes |
| --- | --- | --- |
| `region` | the holding's region | A P-code in any of the forms `ET04`, `region-ET04` or `REGION_ET04` |
| `zone` | the holding's zone | as above |
| `woreda` | the holding's woreda | as above |
| `kebele` | the holding's kebele | as above |
| `recordState` | `record_status` | Case-insensitive. **If omitted, only `ACTIVE` records are counted** (on animal charts: active animals of active holdings), except in `livestockByRecordState` |
| `state` | the holding's approval-workflow state | Case-insensitive, for example `VERIFIED`, `DRAFT`, `KEBELE_APPROVED` |
| `species` | the animal's species | The lookup key (`LIVESTOCK_SPECIES_CATTLE`), its last part (`CATTLE`) or the label (`Cattle`), case-insensitive. On holding-level charts it selects the holdings that keep at least one live animal of the species |

The filters combine with AND. Unknown parameters are ignored.

## Endpoints

### `GET /health`

Checks that the process is serving and that the database answers `SELECT 1`.

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | `{"status": "ok"}` | Healthy |
| 500 | error | The database is unreachable or the pool is exhausted |

---

### `GET /api/v1/charts/livestockKpis`

Headline figures. Returns one object.

| Field | Type | Meaning |
| --- | --- | --- |
| `holdings` | integer | Holdings matching the filters |
| `keepers` | integer | Distinct keepers of those holdings |
| `female_keepers` | integer | … whose farmer record gives gender `FEMALE` |
| `woredas_reporting` | integer | Distinct woredas with at least one holding |
| `animals` | integer | Head count of their animals |
| `species_tracked` | integer | Distinct species among them |
| `breeds_tracked` | integer | Distinct breeds among them |

```json
[{"holdings": 8, "keepers": 8, "female_keepers": 0, "woredas_reporting": 1,
  "animals": 66, "species_tracked": 2, "breeds_tracked": 3}]
```

---

### `GET /api/v1/charts/livestockBySpecies`

Animals per species, largest first.

| Field | Type | Meaning |
| --- | --- | --- |
| `species` | string | Species label |
| `species_code` | string | Species lookup key, e.g. `LIVESTOCK_SPECIES_CATTLE` |
| `animals` | integer | Head count |
| `keepers` | integer | Distinct keepers holding the species |

---

### `GET /api/v1/charts/livestockByBreed`

Animals per breed, largest first. Lines without a breed are left out.

| Field | Type | Meaning |
| --- | --- | --- |
| `breed` | string | Breed label |
| `breed_code` | string | Breed lookup key |
| `species` | string | Species label of the breed |
| `animals` | integer | Head count |

---

### `GET /api/v1/charts/livestockKeepersByRegion`, `…ByZone`, `…ByWoreda`, `…ByKebele`

Keepers and animals per administrative unit at the given level, most keepers first. The dashboards
draw the choropleth from these.

| Field | Type | Meaning |
| --- | --- | --- |
| `<level>` | string | Unit name (`region`, `zone`, `woreda` or `kebele`) |
| `<level>_code` | string | P-code, for joining to map boundaries; `"Unknown"` if unresolved |
| `farmers` | integer | Distinct keepers (the map reads this key) |
| `animals` | integer | Head count of their animals |

```json
[{"region": "Oromia", "region_code": "ET04", "farmers": 8, "animals": 66}]
```

---

### `GET /api/v1/charts/livestockTopWoredas`

The eight woredas with the most keepers, then the most animals.

| Field | Type | Meaning |
| --- | --- | --- |
| `woreda` | string | Woreda name |
| `woreda_code` | string | P-code, or `"Unknown"` |
| `farmers` | integer | Distinct keepers |
| `animals` | integer | Head count |

---

### `GET /api/v1/charts/herdHealthSplit`

Animals per health status (`HEALTHY`, `SICK`, `QUARANTINED`, `DECEASED`).

| Field | Type | Meaning |
| --- | --- | --- |
| `health_status` | string | Status code, or `UNKNOWN` |
| `animals` | integer | Head count |

---

### `GET /api/v1/charts/livestockVaccinationStatus`

Animals per vaccination status (`UP_TO_DATE`, `OVERDUE`, `NONE`).

| Field | Type | Meaning |
| --- | --- | --- |
| `vaccination_status` | string | Status code, or `UNKNOWN` |
| `animals` | integer | Head count |

---

### `GET /api/v1/charts/livestockBySex`

| Field | Type | Meaning |
| --- | --- | --- |
| `sex` | string | `FEMALE`, `MALE`, or `UNKNOWN` (flocks and hives are usually recorded without one) |
| `animals` | integer | Head count |

---

### `GET /api/v1/charts/livestockTrendByMonth`

Holdings per month of registration, oldest first. Holdings without a registration date are left
out.

| Field | Type | Meaning |
| --- | --- | --- |
| `period` | string | `YYYY-MM` |
| `farmers` | integer | Distinct keepers of the holdings registered that month |
| `holdings` | integer | Holdings registered that month |
| `animals` | integer | Head count those holdings hold now |

---

### `GET /api/v1/charts/livestockByState`

Holdings per approval-workflow state.

| Field | Type | Meaning |
| --- | --- | --- |
| `state` | string | `DRAFT`, `KEBELE_APPROVED`, `WOREDA_APPROVED`, `ZONE_APPROVED`, `VERIFIED`, `ARCHIVED`, or `UNKNOWN` |
| `holdings` | integer | Holdings |

---

### `GET /api/v1/charts/livestockByRecordState`

Holdings per record status. This chart ignores the `ACTIVE` default, so it sees every status.

| Field | Type | Meaning |
| --- | --- | --- |
| `record_state` | string | `record_status`, for example `ACTIVE` |
| `holdings` | integer | Holdings |

## Errors

| Status | When |
| --- | --- |
| 401 | Authentication on, and the token is missing or invalid (`WWW-Authenticate` says why) |
| 403 | Valid token without the required role |
| 404 | Unknown chart ID |
| 422 | A query parameter has the wrong type |
| 500 | Database error, for example the reporting views do not exist yet |
| 503 | Authentication on, and the trusted issuers (IAM) or their signing keys cannot be fetched |
