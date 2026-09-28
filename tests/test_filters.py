from app.api.filters import ChartFilters, build_where_clause


def filters(**kwargs) -> ChartFilters:
    params = dict.fromkeys(("region", "zone", "woreda", "kebele", "recordState", "state", "species"))
    params.update(kwargs)
    return ChartFilters(**params)


def test_no_filters_defaults_to_active():
    where = build_where_clause(filters())
    assert where.sql == "WHERE record_status = 'ACTIVE'"
    assert where.values == []


def test_animal_view_defaults_to_active_animals_of_active_holdings():
    where = build_where_clause(filters(), view="animal")
    assert where.sql == "WHERE record_status = 'ACTIVE' AND holding_record_status = 'ACTIVE'"


def test_no_filters_and_no_default_is_empty():
    where = build_where_clause(filters(), default_active=False)
    assert where.sql == ""


def test_all_is_ignored():
    where = build_where_clause(filters(region="all", species="all", state="all"), default_active=False)
    assert where.sql == ""


def test_geography_binds_the_bare_code():
    where = build_where_clause(filters(region="region-ET04", zone="ZONE_ET0407", woreda="ET040706"))
    assert where.values == ["ET04", "ET0407", "ET040706"]
    assert "region_code = $1" in where.sql
    assert "zone_code = $2" in where.sql
    assert "woreda_code = $3" in where.sql


def test_placeholders_are_numbered_in_bind_order():
    where = build_where_clause(filters(region="ET04", state="VERIFIED", species="CATTLE", recordState="active"))
    assert where.values == ["ET04", "VERIFIED", "CATTLE", "active"]
    for n in range(1, 5):
        assert f"${n}" in where.sql
    assert "$5" not in where.sql
    assert "'ACTIVE'" not in where.sql.replace("sa.record_status = 'ACTIVE'", "")


def test_state_column_follows_the_view():
    assert "UPPER(state)" in build_where_clause(filters(state="DRAFT")).sql
    assert "UPPER(holding_state)" in build_where_clause(filters(state="DRAFT"), view="animal").sql


def test_species_on_holdings_is_a_subquery_on_animals():
    sql = build_where_clause(filters(species="GOAT")).sql
    assert "holding_id IN (SELECT sa.holding_id FROM lr_rpt_animal sa" in sql
    assert "holding_id IN" not in build_where_clause(filters(species="GOAT"), view="animal").sql


def test_extra_predicates_are_anded_even_without_filters():
    where = build_where_clause(filters(), default_active=False, extra=("x IS NOT NULL",))
    assert where.sql == "WHERE x IS NOT NULL"


def test_alias_prefixes_every_column():
    where = build_where_clause(filters(region="ET04", state="DRAFT"), view="animal", alias="a")
    assert "a.region_code" in where.sql
    assert "a.holding_state" in where.sql
    assert "a.record_status = 'ACTIVE'" in where.sql
    assert "a.holding_record_status = 'ACTIVE'" in where.sql


def test_values_never_reach_the_sql_text():
    evil = "ET04' OR 1=1 --"
    where = build_where_clause(filters(region=evil, state=evil, species=evil, recordState=evil))
    assert evil not in where.sql
    assert "OR 1=1" not in where.sql
