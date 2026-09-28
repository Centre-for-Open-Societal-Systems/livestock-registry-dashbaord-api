import pytest

# The keys each oan_dashboards component reads. A chart whose keys drift from
# these renders empty in the UI without any error, so pin them here.
CONTRACT = {
    "livestockKpis": {
        "holdings",
        "keepers",
        "female_keepers",
        "woredas_reporting",
        "animals",
        "species_tracked",
        "breeds_tracked",
    },
    "livestockBySpecies": {"species", "species_code", "animals", "keepers"},
    "livestockByBreed": {"breed", "breed_code", "species", "animals"},
    "livestockKeepersByRegion": {"region", "region_code", "farmers", "animals"},
    "livestockKeepersByZone": {"zone", "zone_code", "farmers", "animals"},
    "livestockKeepersByWoreda": {"woreda", "woreda_code", "farmers", "animals"},
    "livestockKeepersByKebele": {"kebele", "kebele_code", "farmers", "animals"},
    "livestockTopWoredas": {"woreda", "woreda_code", "farmers", "animals"},
    "herdHealthSplit": {"health_status", "animals"},
    "livestockVaccinationStatus": {"vaccination_status", "animals"},
    "livestockBySex": {"sex", "animals"},
    "livestockTrendByMonth": {"period", "farmers", "holdings", "animals"},
    "livestockByState": {"state", "holdings"},
    "livestockByRecordState": {"record_state", "holdings"},
}

ALL_FILTERS = {
    "region": "ET04",
    "zone": "ET0407",
    "woreda": "ET040706",
    "kebele": "ET040706888019",
    "recordState": "ACTIVE",
    "state": "VERIFIED",
    "species": "CATTLE",
}


async def get(client, chart, **params):
    response = await client.get(f"/api/v1/charts/{chart}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("chart", sorted(CONTRACT))
async def test_contract_without_filters(client, chart):
    rows = await get(client, chart)
    assert rows, f"{chart} returned no rows"
    for row in rows:
        assert set(row) == CONTRACT[chart]


@pytest.mark.parametrize("chart", sorted(CONTRACT))
async def test_every_filter_at_once(client, chart):
    rows = await get(client, chart, **ALL_FILTERS)
    for row in rows:
        assert set(row) == CONTRACT[chart]


async def test_kpis_count_active_records_by_default(client):
    [kpis] = await get(client, "livestockKpis")
    # h4 is inactive; k1 keeps two holdings; the poultry line counts twelve heads.
    assert kpis == {
        "holdings": 4,
        "keepers": 3,
        "female_keepers": 1,
        "woredas_reporting": 4,
        "animals": 17,
        "species_tracked": 3,
        "breeds_tracked": 3,
    }


@pytest.mark.parametrize("region", ["ET04", "region-ET04", "REGION_ET04"])
async def test_geography_accepts_any_code_form(client, region):
    [kpis] = await get(client, "livestockKpis", region=region)
    assert (kpis["holdings"], kpis["keepers"], kpis["animals"]) == (2, 1, 3)


async def test_species_filter_selects_holdings_that_keep_it(client):
    [kpis] = await get(client, "livestockKpis", species="goat")
    # h3's goat line is retired, so only h2 and h5 keep goats.
    assert (kpis["holdings"], kpis["keepers"], kpis["animals"], kpis["species_tracked"]) == (2, 2, 2, 1)


@pytest.mark.parametrize("species", ["LIVESTOCK_SPECIES_GOAT", "GOAT", "Goat"])
async def test_species_accepts_key_code_or_label(client, species):
    rows = await get(client, "livestockBySpecies", species=species)
    assert [(r["species_code"], r["animals"]) for r in rows] == [("LIVESTOCK_SPECIES_GOAT", 2)]


async def test_state_filter(client):
    [kpis] = await get(client, "livestockKpis", state="verified")
    assert kpis["holdings"] == 2


async def test_record_state_filter(client):
    [kpis] = await get(client, "livestockKpis", recordState="INACTIVE")
    assert (kpis["holdings"], kpis["animals"]) == (1, 1)


async def test_species_counts_heads(client):
    rows = await get(client, "livestockBySpecies")
    assert [(r["species"], r["animals"], r["keepers"]) for r in rows] == [
        ("Chicken", 12, 1),
        ("Cattle", 3, 2),
        ("Goat", 2, 2),
    ]


async def test_breeds(client):
    rows = await get(client, "livestockByBreed")
    assert [(r["breed"], r["species"], r["animals"]) for r in rows] == [
        ("Begait", "Goat", 2),
        ("Boran", "Cattle", 2),
        ("Horro", "Cattle", 1),
    ]


async def test_keepers_by_region_keeps_unresolved_units(client):
    rows = await get(client, "livestockKeepersByRegion")
    by_code = {r["region_code"]: (r["region"], r["farmers"], r["animals"]) for r in rows}
    assert by_code == {
        "ET04": ("Oromia", 1, 3),
        "ET02": ("Afar", 1, 13),
        "Unknown": ("Oromiya", 1, 1),
    }


async def test_top_woredas(client):
    rows = await get(client, "livestockTopWoredas")
    assert [(r["woreda_code"], r["animals"]) for r in rows] == [
        ("ET020207", 13),
        ("ET040706", 2),
        ("ET040703", 1),
        ("Unknown", 1),
    ]


async def test_health_split(client):
    rows = await get(client, "herdHealthSplit")
    assert {r["health_status"]: r["animals"] for r in rows} == {"HEALTHY": 15, "SICK": 1, "QUARANTINED": 1}


async def test_sex_split_reports_unknown(client):
    rows = await get(client, "livestockBySex")
    assert [(r["sex"], r["animals"]) for r in rows] == [("UNKNOWN", 12), ("FEMALE", 3), ("MALE", 2)]


async def test_trend_by_month(client):
    rows = await get(client, "livestockTrendByMonth")
    assert rows == [
        {"period": "2026-03", "farmers": 1, "holdings": 1, "animals": 2},
        {"period": "2026-04", "farmers": 2, "holdings": 2, "animals": 14},
    ]


async def test_state_breakdown(client):
    rows = await get(client, "livestockByState")
    assert {r["state"]: r["holdings"] for r in rows} == {"VERIFIED": 2, "DRAFT": 1, "KEBELE_APPROVED": 1}


async def test_record_state_breakdown_sees_every_status(client):
    rows = await get(client, "livestockByRecordState")
    assert {r["record_state"]: r["holdings"] for r in rows} == {"ACTIVE": 4, "INACTIVE": 1}


async def test_unknown_chart_is_404(client):
    response = await client.get("/api/v1/charts/farmerKpis")
    assert response.status_code == 404


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
