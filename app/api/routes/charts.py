"""Chart endpoints for the livestock registry dashboard.

Each endpoint returns a JSON array of row objects whose keys match what the
oan_dashboards components read. Read only from the lr_rpt_* reporting views;
see AGENTS.md for the rules.

  lr_rpt_holding  one row per holding: keeper, geography, workflow state
  lr_rpt_animal   one row per animal line; `heads` is the head count to SUM
                  (a poultry or beehive line counts several)
"""

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends

from app.api.dependencies import get_db_pool
from app.api.filters import ChartFilters, Where, build_where_clause
from app.core import geo

router = APIRouter()

Rows = list[dict[str, Any]]


async def fetch(pool: asyncpg.Pool, query: str, where: Where) -> Rows:
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *where.values)
    return [dict(r) for r in records]


@router.get("/livestockKpis", response_model=Rows)
async def get_livestock_kpis(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    holdings = build_where_clause(filters)
    animals = build_where_clause(filters, view="animal")
    [h] = await fetch(
        pool,
        f"""
        SELECT
            COUNT(*)::bigint                                                  AS holdings,
            COUNT(DISTINCT keeper_key)::bigint                                AS keepers,
            COUNT(DISTINCT keeper_key) FILTER (WHERE keeper_gender = 'FEMALE')::bigint AS female_keepers,
            COUNT(DISTINCT COALESCE(woreda_code, woreda_name))::bigint        AS woredas_reporting
        FROM lr_rpt_holding
        {holdings.sql}
        """,
        holdings,
    )
    [a] = await fetch(
        pool,
        f"""
        SELECT
            COALESCE(SUM(heads), 0)::bigint      AS animals,
            COUNT(DISTINCT species)::bigint      AS species_tracked,
            COUNT(DISTINCT breed)::bigint        AS breeds_tracked
        FROM lr_rpt_animal
        {animals.sql}
        """,
        animals,
    )
    return [{**h, **a}]


@router.get("/livestockBySpecies", response_model=Rows)
async def get_livestock_by_species(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    where = build_where_clause(filters, view="animal", extra=("species IS NOT NULL",))
    query = f"""
        SELECT
            MAX(species_name)                    AS species,
            species                              AS species_code,
            COALESCE(SUM(heads), 0)::bigint      AS animals,
            COUNT(DISTINCT keeper_key)::bigint   AS keepers
        FROM lr_rpt_animal
        {where.sql}
        GROUP BY species
        ORDER BY animals DESC, species_code
    """
    return await fetch(pool, query, where)


@router.get("/livestockByBreed", response_model=Rows)
async def get_livestock_by_breed(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    where = build_where_clause(filters, view="animal", extra=("breed IS NOT NULL",))
    query = f"""
        SELECT
            MAX(breed_name)                      AS breed,
            breed                                AS breed_code,
            MAX(species_name)                    AS species,
            COALESCE(SUM(heads), 0)::bigint      AS animals
        FROM lr_rpt_animal
        {where.sql}
        GROUP BY breed
        ORDER BY animals DESC, breed_code
    """
    return await fetch(pool, query, where)


async def keepers_by_geo_level(pool: asyncpg.Pool, filters: ChartFilters, level: str) -> Rows:
    """Keepers and animals per administrative unit at dashboard level `level`.

    `farmers` holds the keeper count because the map reads that key whatever
    the measure is. `<level>_code` is the P-code map boundaries are keyed on.
    `level` comes from the fixed handlers below, never from the request.
    """
    where = build_where_clause(filters)
    name, code = geo.name_column(level), geo.code_column(level)
    query = f"""
        SELECT
            COALESCE(MAX({name}), 'Unknown')          AS {level},
            COALESCE({code}, 'Unknown')               AS {level}_code,
            COUNT(DISTINCT keeper_key)::bigint        AS farmers,
            COALESCE(SUM(heads), 0)::bigint           AS animals
        FROM lr_rpt_holding
        {where.sql}
        GROUP BY {code}, CASE WHEN {code} IS NULL THEN {name} END
        ORDER BY farmers DESC, {level}_code
    """
    return await fetch(pool, query, where)


@router.get("/livestockKeepersByRegion", response_model=Rows)
async def get_keepers_by_region(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    return await keepers_by_geo_level(pool, filters, "region")


@router.get("/livestockKeepersByZone", response_model=Rows)
async def get_keepers_by_zone(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    return await keepers_by_geo_level(pool, filters, "zone")


@router.get("/livestockKeepersByWoreda", response_model=Rows)
async def get_keepers_by_woreda(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    return await keepers_by_geo_level(pool, filters, "woreda")


@router.get("/livestockKeepersByKebele", response_model=Rows)
async def get_keepers_by_kebele(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    return await keepers_by_geo_level(pool, filters, "kebele")


@router.get("/livestockTopWoredas", response_model=Rows)
async def get_top_woredas(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    where = build_where_clause(filters, extra=("(woreda_code IS NOT NULL OR woreda_name IS NOT NULL)",))
    query = f"""
        SELECT
            MAX(woreda_name)                          AS woreda,
            COALESCE(woreda_code, 'Unknown')          AS woreda_code,
            COUNT(DISTINCT keeper_key)::bigint        AS farmers,
            COALESCE(SUM(heads), 0)::bigint           AS animals
        FROM lr_rpt_holding
        {where.sql}
        GROUP BY woreda_code, CASE WHEN woreda_code IS NULL THEN woreda_name END
        ORDER BY farmers DESC, animals DESC, woreda_code
        LIMIT 8
    """
    return await fetch(pool, query, where)


async def animals_by(pool: asyncpg.Pool, filters: ChartFilters, column: str) -> Rows:
    """Head count per value of an animal attribute. `column` is a fixed literal."""
    where = build_where_clause(filters, view="animal")
    query = f"""
        SELECT COALESCE({column}, 'UNKNOWN') AS {column}, COALESCE(SUM(heads), 0)::bigint AS animals
        FROM lr_rpt_animal
        {where.sql}
        GROUP BY 1
        ORDER BY animals DESC, 1
    """
    return await fetch(pool, query, where)


@router.get("/herdHealthSplit", response_model=Rows)
async def get_herd_health_split(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    # HEALTHY, SICK, QUARANTINED, DECEASED; the UI labels them.
    return await animals_by(pool, filters, "health_status")


@router.get("/livestockVaccinationStatus", response_model=Rows)
async def get_vaccination_status(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    return await animals_by(pool, filters, "vaccination_status")


@router.get("/livestockBySex", response_model=Rows)
async def get_livestock_by_sex(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    return await animals_by(pool, filters, "sex")


@router.get("/livestockTrendByMonth", response_model=Rows)
async def get_trend_by_month(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    # Holdings by the month they were registered, with the animals they hold now.
    where = build_where_clause(filters, extra=("registration_date IS NOT NULL",))
    query = f"""
        SELECT
            TO_CHAR(DATE_TRUNC('month', registration_date), 'YYYY-MM') AS period,
            COUNT(DISTINCT keeper_key)::bigint                         AS farmers,
            COUNT(*)::bigint                                           AS holdings,
            COALESCE(SUM(heads), 0)::bigint                            AS animals
        FROM lr_rpt_holding
        {where.sql}
        GROUP BY 1
        ORDER BY 1
    """
    return await fetch(pool, query, where)


@router.get("/livestockByState", response_model=Rows)
async def get_livestock_by_state(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    # Holdings per approval-workflow state (DRAFT, KEBELE_APPROVED, ..., VERIFIED).
    where = build_where_clause(filters)
    query = f"""
        SELECT COALESCE(state, 'UNKNOWN') AS state, COUNT(*)::bigint AS holdings
        FROM lr_rpt_holding
        {where.sql}
        GROUP BY 1
        ORDER BY holdings DESC, 1
    """
    return await fetch(pool, query, where)


@router.get("/livestockByRecordState", response_model=Rows)
async def get_livestock_by_record_state(filters: ChartFilters = Depends(), pool: asyncpg.Pool = Depends(get_db_pool)):
    # A breakdown by status must see every status, so no ACTIVE default here.
    where = build_where_clause(filters, default_active=False)
    query = f"""
        SELECT COALESCE(record_status, 'UNKNOWN') AS record_state, COUNT(*)::bigint AS holdings
        FROM lr_rpt_holding
        {where.sql}
        GROUP BY 1
        ORDER BY holdings DESC, 1
    """
    return await fetch(pool, query, where)
