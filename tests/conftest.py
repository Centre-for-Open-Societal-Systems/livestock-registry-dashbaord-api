"""Test fixtures.

Tests run against a real Postgres (the query SQL is the thing under test), but
never against the registry's data: each test gets a throw-away schema holding
small lr_rpt_* tables with the reporting views' columns, and the pool's
search_path points at it. The schema is dropped afterwards.

TEST_DATABASE_URL names the server, with a role that may create schemas. It is
never defaulted: without it, the database tests are skipped and only the pure
unit tests run.
"""

import os
import uuid
from datetime import date

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# The app's settings require DATABASE_URL at import time; the tests replace
# the pool, so the value is never used to connect.
os.environ.setdefault("DATABASE_URL", "postgresql://unused@localhost/unused")

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402

from app.api.dependencies import get_db_pool  # noqa: E402
from app.main import app  # noqa: E402

# Unit paths: (name, code) per level. "unresolved" is a holding whose names
# Master Data did not know, so it has names but no codes.
GEO = {
    "adaa": (("Oromia", "ET04"), ("East Shewa", "ET0407"), ("Ada'a", "ET040706"), ("Dire Arerti", "ET040706888019")),
    "adama": (("Oromia", "ET04"), ("East Shewa", "ET0407"), ("Adama", "ET040703"), ("Bofa", "ET040703888001")),
    "afdera": (("Afar", "ET02"), ("Kilbet Rasu", "ET0202"), ("Afdera", "ET020207"), ("Adkuma", "ET020207888009")),
    "unresolved": (("Oromiya", None), ("E. Shoa", None), ("Adaa", None), ("DA", None)),
}

SCHEMA_SQL = """
CREATE TABLE lr_rpt_holding (
    holding_id varchar PRIMARY KEY,
    record_status varchar,
    state text,
    registration_date date,
    keeper_key text,
    keeper_gender text,
    region_name text, zone_name text, woreda_name text, kebele_name text,
    region_code text, zone_code text, woreda_code text, kebele_code text,
    animal_lines bigint,
    heads bigint,
    species_count bigint
);
CREATE TABLE lr_rpt_animal (
    animal_id varchar PRIMARY KEY,
    holding_id varchar,
    record_status varchar,
    holding_record_status varchar,
    holding_state text,
    registration_date date,
    keeper_key text,
    species text, species_name text,
    breed text, breed_name text,
    sex text,
    health_status text,
    vaccination_status text,
    heads bigint,
    region_name text, zone_name text, woreda_name text, kebele_name text,
    region_code text, zone_code text, woreda_code text, kebele_code text
);
"""

CATTLE, GOAT, CHICKEN = "LIVESTOCK_SPECIES_CATTLE", "LIVESTOCK_SPECIES_GOAT", "LIVESTOCK_SPECIES_CHICKEN"
SPECIES_NAME = {CATTLE: "Cattle", GOAT: "Goat", CHICKEN: "Chicken"}
BREED_NAME = {
    "LIVESTOCK_BREED_BORAN": "Boran",
    "LIVESTOCK_BREED_BEGAIT_GOAT": "Begait",
    "LIVESTOCK_BREED_HORRO": "Horro",
}

# holding, status, state, registered, keeper, keeper gender, geo
# k1 keeps two holdings: keepers are counted once.
HOLDINGS = [
    ("h1", "ACTIVE", "VERIFIED", "2026-03-10", "k1", "FEMALE", "adaa"),
    ("h2", "ACTIVE", "DRAFT", "2026-04-02", "k1", "FEMALE", "adama"),
    ("h3", "ACTIVE", "KEBELE_APPROVED", "2026-04-20", "k2", "MALE", "afdera"),
    ("h4", "INACTIVE", "VERIFIED", "2026-04-25", "k3", "MALE", "adaa"),
    ("h5", "ACTIVE", "VERIFIED", None, "k4", None, "unresolved"),
]

# animal, holding, status, species, breed, sex, health, vaccination, quantity
# a5 is a poultry line: one line, twelve heads. a6 is a retired line.
ANIMALS = [
    ("a1", "h1", "ACTIVE", CATTLE, "LIVESTOCK_BREED_BORAN", "FEMALE", "HEALTHY", "UP_TO_DATE", None),
    ("a2", "h1", "ACTIVE", CATTLE, "LIVESTOCK_BREED_BORAN", "MALE", "SICK", "NONE", None),
    ("a3", "h2", "ACTIVE", GOAT, "LIVESTOCK_BREED_BEGAIT_GOAT", "MALE", "HEALTHY", "NONE", None),
    ("a4", "h3", "ACTIVE", CATTLE, "LIVESTOCK_BREED_HORRO", "FEMALE", "HEALTHY", "UP_TO_DATE", None),
    ("a5", "h3", "ACTIVE", CHICKEN, None, None, "HEALTHY", None, 12),
    ("a6", "h3", "INACTIVE", GOAT, "LIVESTOCK_BREED_BEGAIT_GOAT", "MALE", "DECEASED", None, None),
    ("a7", "h4", "ACTIVE", CATTLE, "LIVESTOCK_BREED_BORAN", "FEMALE", "HEALTHY", "UP_TO_DATE", None),
    ("a8", "h5", "ACTIVE", GOAT, "LIVESTOCK_BREED_BEGAIT_GOAT", "FEMALE", "QUARANTINED", "OVERDUE", None),
]


def _params(n: int) -> str:
    return ",".join(f"${i}" for i in range(1, n + 1))


async def _seed(conn: asyncpg.Connection) -> None:
    await conn.execute(SCHEMA_SQL)
    holding = {}
    for hid, status, state, reg, keeper, gender, place in HOLDINGS:
        names = [n for n, _ in GEO[place]]
        codes = [c for _, c in GEO[place]]
        live = [a for a in ANIMALS if a[1] == hid and a[2] == "ACTIVE"]
        heads = sum(a[8] or 1 for a in live)
        holding[hid] = (status, state, reg, keeper, names, codes)
        await conn.execute(
            f"INSERT INTO lr_rpt_holding VALUES ({_params(17)})",
            hid,
            status,
            state,
            reg and date.fromisoformat(reg),
            keeper,
            gender,
            *names,
            *codes,
            len(live),
            heads,
            len({a[3] for a in live}),
        )
    for aid, hid, status, species, breed, sex, health, vacc, qty in ANIMALS:
        h_status, h_state, reg, keeper, names, codes = holding[hid]
        await conn.execute(
            f"INSERT INTO lr_rpt_animal VALUES ({_params(23)})",
            aid,
            hid,
            status,
            h_status,
            h_state,
            reg and date.fromisoformat(reg),
            keeper,
            species,
            SPECIES_NAME[species],
            breed,
            BREED_NAME.get(breed),
            sex,
            health,
            vacc,
            qty or 1,
            *names,
            *codes,
        )


@pytest.fixture
async def pool():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    dsn = TEST_DATABASE_URL
    schema = f"test_dash_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(dsn)
    await admin.execute(f"CREATE SCHEMA {schema}")
    try:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2, server_settings={"search_path": schema})
        async with pool.acquire() as conn:
            await _seed(conn)
        yield pool
        await pool.close()
    finally:
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()


@pytest.fixture
async def client(pool):
    app.dependency_overrides[get_db_pool] = lambda: pool
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
