from dataclasses import dataclass, field
from typing import Literal

from fastapi import Query

from app.core import geo

# The reporting view a chart reads: one row per holding, or per animal line.
View = Literal["holding", "animal"]

# Workflow state (DRAFT .. VERIFIED) is the holding's; the animal view carries it down.
STATE_COLUMN: dict[str, str] = {
    "holding": "state",
    "animal": "holding_state",
}


def _given(value: str | None) -> bool:
    return bool(value) and value != "all"


class ChartFilters:
    """Query parameters shared by every chart endpoint."""

    def __init__(
        self,
        region: str | None = Query(None),
        zone: str | None = Query(None),
        woreda: str | None = Query(None),
        kebele: str | None = Query(None),
        recordState: str | None = Query(None),
        state: str | None = Query(None),
        species: str | None = Query(None),
    ):
        self.region = region
        self.zone = zone
        self.woreda = woreda
        self.kebele = kebele
        self.recordState = recordState
        self.state = state
        self.species = species


@dataclass
class Where:
    """A WHERE clause and its bind values. `sql` is empty when nothing applies."""

    sql: str
    values: list = field(default_factory=list)


def _species_match(prefix: str, placeholder: str) -> str:
    # A species may be asked for by its lookup key (LIVESTOCK_SPECIES_CATTLE),
    # the key's last part (CATTLE) or its label (Cattle).
    return (
        f"(UPPER({prefix}species) = UPPER({placeholder})"
        f" OR UPPER(regexp_replace({prefix}species, '^LIVESTOCK_SPECIES_', '')) = UPPER({placeholder})"
        f" OR UPPER({prefix}species_name) = UPPER({placeholder}))"
    )


def build_where_clause(
    filters: ChartFilters,
    view: View = "holding",
    extra: tuple[str, ...] = (),
    default_active: bool = True,
    alias: str = "",
) -> Where:
    """Build a parameterised WHERE clause for a reporting view.

    Only literal column names are interpolated; every filter value is bound as
    $n. `extra` holds fixed predicates (no user input) that must be ANDed in, so
    callers never concatenate onto the clause themselves: an empty clause plus
    "AND ..." is invalid SQL.

    Without an explicit recordState, only ACTIVE records are counted (on the
    animal view, ACTIVE animals of ACTIVE holdings). Pass default_active=False
    for charts that break down by status.
    """
    prefix = f"{alias}." if alias else ""
    conditions: list[str] = []
    values: list = []

    def bind(value) -> str:
        values.append(value)
        return f"${len(values)}"

    for level in geo.LEVELS:
        value = getattr(filters, level)
        if _given(value):
            conditions.append(f"{prefix}{geo.code_column(level)} = {bind(geo.code(value))}")

    if _given(filters.state):
        conditions.append(f"UPPER({prefix}{STATE_COLUMN[view]}) = UPPER({bind(filters.state)})")

    if _given(filters.species):
        p = bind(filters.species)
        if view == "animal":
            conditions.append(_species_match(prefix, p))
        else:
            # A holding matches when it keeps at least one live animal of the species.
            conditions.append(
                f"{prefix}holding_id IN (SELECT sa.holding_id FROM lr_rpt_animal sa"
                f" WHERE sa.record_status = 'ACTIVE' AND {_species_match('sa.', p)})"
            )

    if _given(filters.recordState):
        conditions.append(f"LOWER({prefix}record_status) = LOWER({bind(filters.recordState)})")
    elif default_active:
        conditions.append(f"{prefix}record_status = 'ACTIVE'")
        if view == "animal":
            conditions.append(f"{prefix}holding_record_status = 'ACTIVE'")

    conditions.extend(extra)

    if not conditions:
        return Where("")
    return Where("WHERE " + " AND ".join(conditions), values)
