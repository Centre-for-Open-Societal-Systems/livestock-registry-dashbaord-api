import pytest

from app.core import geo


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ET04", "ET04"),
        ("region-ET04", "ET04"),
        ("REGION_ET04", "ET04"),
        ("kebele-ET040706888019", "ET040706888019"),
        ("  zone-ET0407 ", "ET0407"),
    ],
)
def test_code_strips_the_level_prefix(value, expected):
    assert geo.code(value) == expected


def test_columns():
    columns = [geo.code_column(level) for level in geo.LEVELS]
    assert columns == ["region_code", "zone_code", "woreda_code", "kebele_code"]
    assert geo.name_column("woreda") == "woreda_name"
