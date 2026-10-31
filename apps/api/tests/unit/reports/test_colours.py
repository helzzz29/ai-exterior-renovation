"""Plain colour names in the report."""

import pytest

from app.domain.models import LineItem, PackCount
from app.reports.colours import colour_name, describe_colour
from app.reports.pdf import buy_text, round_friendly

# the swatches the app offers, with the names it shows (apps/web COLOUR_PRESETS)
APP_SWATCHES = {
    "#f5f0e6": "Off-white",
    "#e9dcc0": "Warm beige",
    "#d6e0d8": "Pale sage",
    "#cdb79e": "Sandstone",
    "#c97b5a": "Terracotta",
    "#9ca3af": "Light grey",
    "#5b6270": "Slate grey",
    "#1f2937": "Charcoal",
}


@pytest.mark.parametrize(("hex_colour", "name"), APP_SWATCHES.items())
def test_app_swatches_keep_their_names(hex_colour: str, name: str) -> None:
    assert colour_name(hex_colour) == name
    assert colour_name(hex_colour.upper()) == name


def test_any_colour_gets_the_nearest_name() -> None:
    assert colour_name("#CDBFA6") == "Sandstone"  # a material's default colour
    assert colour_name("#fefefe") == "White"
    assert colour_name("#3366aa") == "Blue"
    assert colour_name("#c62828") == "Red"


def test_description_keeps_the_code_for_the_paint_shop() -> None:
    assert describe_colour("#e9dcc0") == "Warm beige (E9DCC0)"
    assert describe_colour(None) == "-"
    assert describe_colour("not-a-colour") == "not-a-colour"


def test_range_rounding_matches_the_app() -> None:
    # apps/web roundFriendly: nearest 1,000 from 10,000 up, else 100; halves round up
    assert (round_friendly(32355), round_friendly(39545)) == (32000, 40000)
    assert round_friendly(31500) == 32000
    assert round_friendly(9450) == 9500
    assert round_friendly(9449) == 9400


def _line(**kw) -> LineItem:  # noqa: ANN003
    base = dict(
        material_id="p",
        material_name="Paint",
        category="paint",
        label="wall",
        region_ids=["w"],
        measured_quantity=100,
        measured_unit="sqft",
        wastage_pct=5,
        with_wastage=105,
        required_quantity=4.85,
        purchase_quantity=5,
        purchase_unit="L",
        material_rate=400,
        material_cost=2000,
        labour_rate=10,
        labour_cost=1000,
        total=3000,
    )
    return LineItem(**{**base, **kw})


def test_buy_text_shows_each_pack_size() -> None:
    mixed = _line(packs=2, pack_mix=[PackCount(size=4, count=1), PackCount(size=1, count=1)])
    assert buy_text(mixed) == "5 L (1 x 4 + 1 x 1)"
    same = _line(purchase_quantity=8, packs=2, pack_size=4)
    assert buy_text(same) == "8 L (2 x 4)"
    assert buy_text(_line(purchase_quantity=91, purchase_unit="sqft")) == "91 sqft"
