from __future__ import annotations

import pytest

from app.domain.models import Companion, RateOverride
from app.estimation import (
    ceil_safe,
    companion_quantity,
    material_quantity,
    price_line,
    round_money,
    round_to_packs,
    with_wastage,
)
from app.estimation.quantities import fmt, money

from .helpers import make_material, paint_material


def test_ceil_safe_tolerates_float_noise():
    assert ceil_safe(0) == 0
    assert ceil_safe(-1) == 0
    assert ceil_safe(1e-12) == 1  # any positive need buys at least one unit
    assert ceil_safe(8.000000000001) == 8
    assert ceil_safe(8.01) == 9
    assert ceil_safe(0.3 * 3 / 0.9) == 1


def test_round_to_packs():
    assert round_to_packs(8, 4) == (2, 8)  # exact multiple
    assert round_to_packs(8.0001, 4) == (3, 12)
    assert round_to_packs(0.01, 4) == (1, 4)  # tiny area still needs one can
    assert round_to_packs(0, 4) == (0, 0)  # zero area buys nothing
    assert round_to_packs(2.2, None) == (None, 3)
    assert round_to_packs(2.2, 0) == (None, 3)


def test_with_wastage():
    assert with_wastage(100, 12) == pytest.approx(112)
    assert with_wastage(0, 12) == 0


def test_round_money_half_up():
    assert round_money(2.5) == 3
    assert round_money(3558.78) == 3559
    assert round_money(1658.05) == 1658
    assert round_money(32868.8, 100) == 32900
    assert round_money(49250, 100) == 49300


def test_fmt_and_money():
    assert fmt(254.19) == "254.2"
    assert fmt(4.0) == "4"
    assert fmt(1234.5, 2) == "1,234.5"
    assert money(41086.4) == "₹41,086"


# ---------------------------------------------------------------- every pricing unit


def test_litre_paint():
    m = paint_material()  # 100 sqft/L/coat, 2 coats, 4 L cans
    q = material_quantity(m, 200, "sqft")
    assert (q.required, q.packs, q.purchase, q.purchase_unit) == (4, 1, 4, "L")
    q = material_quantity(m, 201, "sqft")
    assert (q.packs, q.purchase) == (2, 8)


def test_litre_without_pack_size():
    q = material_quantity(paint_material(pack_size=None), 150, "sqft")
    assert (q.packs, q.purchase) == (None, 3)
    assert q.derivation[0].endswith("→ 3 L")


def test_kg_texture():
    m = make_material(pricing_unit="kg", coverage_sqft_per_unit=10, pack_size=25)
    q = material_quantity(m, 250, "sqft")
    assert (q.required, q.packs, q.purchase) == (25, 1, 25)
    assert "1 × 25 kg bag" in q.derivation[0]
    q = material_quantity(m, 251, "sqft")
    assert (q.packs, q.purchase) == (2, 50)
    assert "bags" in q.derivation[0]


def test_piece_tiles_with_boxes():
    m = make_material(pricing_unit="piece", piece_area_sqft=2, pieces_per_box=5)
    q = material_quantity(m, 20, "sqft")  # exactly 10 pieces = 2 boxes
    assert (q.required, q.packs, q.purchase, q.pack_size) == (10, 2, 10, 5)
    q = material_quantity(m, 20.5, "sqft")  # 11 pieces -> 3 boxes
    assert (q.packs, q.purchase) == (3, 15)
    assert "3 boxes of 5 = 15 pieces" in q.derivation[0]


def test_piece_without_boxes():
    m = make_material(pricing_unit="piece", piece_area_sqft=2)
    q = material_quantity(m, 21, "sqft")
    assert (q.packs, q.purchase) == (None, 11)


def test_sheet_panels():
    m = make_material(pricing_unit="sheet", piece_area_sqft=32)
    assert material_quantity(m, 64, "sqft").purchase == 2
    assert material_quantity(m, 64.1, "sqft").purchase == 3
    assert material_quantity(m, 0, "sqft").purchase == 0


def test_sqft_and_rft_whole_units():
    sq = make_material(pricing_unit="sqft")
    assert material_quantity(sq, 80.64, "sqft").purchase == 81
    assert material_quantity(sq, 81.0, "sqft").purchase == 81
    rf = make_material(pricing_unit="rft", measure_basis="length")
    q = material_quantity(rf, 7.65, "rft")
    assert (q.purchase, q.purchase_unit) == (8, "rft")
    assert "running ft" in q.derivation[0]


def test_missing_unit_fields_raise():
    with pytest.raises(ValueError):
        material_quantity(make_material(pricing_unit="litre"), 10, "sqft")
    with pytest.raises(ValueError):
        material_quantity(make_material(pricing_unit="piece"), 10, "sqft")
    with pytest.raises(ValueError):
        material_quantity(make_material(pricing_unit="sheet", piece_area_sqft=0), 10, "sqft")


def test_companion_quantity():
    c = Companion(
        kind="adhesive",
        name="Tile adhesive",
        unit="kg",
        quantity_per_sqft=0.5,
        pack_size=20,
        rate=22,
    )
    assert companion_quantity(c, 80) == (40, 2, 40)
    assert companion_quantity(c, 81) == (40.5, 3, 60)
    assert companion_quantity(c, 0) == (0, 0, 0)


# ---------------------------------------------------------------- price_line


def test_price_line_paint_with_primer():
    line = price_line(paint_material(), "wall", ["w"], 200)
    assert line.purchase_quantity == 4
    assert line.material_cost == 1600
    (primer,) = line.companions
    assert (primer.quantity, primer.packs, primer.purchase_quantity, primer.cost) == (2, 1, 4, 1000)
    assert line.labour_cost == 2000
    assert line.total == 4600
    assert line.rate_overridden is False
    assert line.measured_unit == "sqft"
    assert any(
        s.startswith("Exterior primer: 200 sq ft ÷ 100 sq ft per litre") for s in line.derivation
    )
    assert line.derivation[-1] == "Total: ₹1,600 + ₹1,000 + ₹2,000 = ₹4,600"


def test_price_line_adhesive_derivation_multiplies():
    m = make_material(
        pricing_unit="piece",
        piece_area_sqft=2,
        pieces_per_box=5,
        category="tiles",
        companions=[
            Companion(
                kind="adhesive",
                name="Tile adhesive",
                unit="kg",
                quantity_per_sqft=0.5,
                pack_size=20,
                rate=22,
            )
        ],
    )
    line = price_line(m, "wall", ["a", "b"], 40)
    assert line.companions[0].cost == 440
    assert any("× 0.5 kg per sq ft" in s for s in line.derivation)
    assert line.derivation[0].startswith("Area (2 parts) 40 sq ft")


def test_price_line_overrides():
    m = paint_material()
    line = price_line(m, "wall", ["w"], 200, RateOverride(material_id="paint", material_rate=500))
    assert (line.material_rate, line.material_cost, line.labour_cost) == (500, 2000, 2000)
    assert line.rate_overridden
    line = price_line(m, "wall", ["w"], 200, RateOverride(material_id="paint", labour_rate=0))
    assert (line.material_rate, line.labour_cost, line.rate_overridden) == (400, 0, True)
    line = price_line(m, "wall", ["w"], 200, RateOverride(material_id="paint"))
    assert line.rate_overridden is False


def test_price_line_zero_area():
    line = price_line(paint_material(), "wall", ["w"], 0)
    assert (line.purchase_quantity, line.packs, line.total) == (0, 0, 0)
    assert line.companions[0].packs == 0
