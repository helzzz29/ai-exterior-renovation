"""A worked estimation example, step by step and end to end."""

from __future__ import annotations

import pytest

from app.domain.models import (
    Assignment,
    BoxPx,
    Confidence,
    EstimateInputs,
    Extras,
    ScaleInputs,
    ScaleMethod,
)
from app.estimation import (
    DEFAULT_CATALOGUE_PATH,
    apply_extras,
    area_from_px,
    compute_estimate,
    length_from_px,
    load_catalogue,
    measure_surfaces,
    pillar_area,
    price_line,
    resolve_scale,
    round_money,
    with_wastage,
)

from .helpers import box_region, region, trapezoid_wall

FT = 7 / 461


@pytest.fixture(scope="module")
def cat():
    return load_catalogue(DEFAULT_CATALOGUE_PATH)


def test_catalogue_matches_worked_example(cat):
    paint = cat["paint-premium-emulsion"]
    assert paint.name == "Premium exterior emulsion"
    assert (paint.coverage_sqft_per_unit, paint.coats, paint.pack_size) == (110, 2, 4)
    assert (paint.material_rate, paint.labour_rate, paint.wastage_pct) == (420, 14, 5)
    primer = paint.companions[0]
    assert primer.quantity_per_sqft == pytest.approx(1 / 120)
    assert (primer.pack_size, primer.rate) == (4, 250)
    stone = cat["cladding-natural-stone"]
    assert (stone.material_rate, stone.labour_rate, stone.wastage_pct) == (110, 45, 12)
    glass = cat["railing-toughened-glass"]
    assert (glass.material_rate, glass.labour_rate, glass.wastage_pct) == (1200, 200, 5)


def test_step_scale_from_door():
    door = box_region("door", "door", 900, 1539, 1100, 2000)  # 461 px tall
    wall = box_region("wall", "wall", 0, 0, 2048, 2000)
    scale = resolve_scale(
        ScaleInputs(
            regions=[wall, door],
            door_visible=0.95,
            door_box_px=BoxPx(x0=900, y0=1539, x1=1100, y1=2000),
        )
    )
    assert scale.method == ScaleMethod.door
    assert scale.confidence == Confidence.medium
    assert scale.ft_per_px == pytest.approx(0.015184, abs=5e-7)
    assert scale.ft_per_px == 7 / 461


def test_step_main_wall_paint(cat):
    area = area_from_px(1_050_000, FT, 1.05)
    assert round(area, 1) == 254.2
    assert round(with_wastage(area, 5), 1) == 266.9
    line = price_line(cat["paint-premium-emulsion"], "wall", ["wall"], area)
    assert round(line.required_quantity, 2) == 4.85
    # 4 L + 1 L covers 4.85 L with the least paint bought (it used to be 2 x 4 L = 8 L)
    assert (line.packs, line.purchase_quantity) == (2, 5)
    assert [(p.size, p.count) for p in line.pack_mix] == [(4, 1), (1, 1)]
    primer = line.companions[0]
    assert round(primer.quantity, 2) == 2.22
    assert (primer.packs, primer.purchase_quantity, primer.cost) == (1, 4, 1000)
    assert line.material_cost + primer.cost == 3100
    assert line.labour_cost == 3559
    assert line.total == 6659
    assert line.derivation[0] == "Area 254.2 sq ft + 5% wastage = 266.9 sq ft"
    assert line.derivation[1] == (
        "266.9 sq ft × 2 coats ÷ 110 sq ft per litre = 4.85 L → 1 × 4 L + 1 × 1 L cans"
    )


def test_step_pillars_stone(cat):
    each = pillar_area(10, 1.2)
    assert each == pytest.approx(36.0)
    line = price_line(cat["cladding-natural-stone"], "pillar", ["p1", "p2"], 2 * each)
    assert round(line.with_wastage, 1) == 80.6
    assert line.purchase_quantity == 81
    assert line.material_cost == 8910
    assert line.labour_cost == 3240
    assert line.total == 12150


def test_step_railing_glass(cat):
    length = length_from_px(480, FT)
    assert round(length, 2) == 7.29
    line = price_line(cat["railing-toughened-glass"], "railing", ["r"], length)
    assert round(line.with_wastage, 2) == 7.65
    assert line.purchase_quantity == 8
    assert line.material_cost == 9600
    assert line.labour_cost == 1458
    assert line.total == 11058
    assert line.measured_unit == "rft"


def test_step_totals():
    area = area_from_px(1_050_000, FT, 1.05)
    t = apply_extras(6659 + 12150 + 11058, area, 2, Extras(), Confidence.medium)
    assert t.lines_total == 29867
    assert t.scaffolding == 2034
    assert t.contingency == 1595
    assert t.tax == 6029
    assert round(t.grand_total) == 39525
    assert (round_money(t.range_low, 100), round_money(t.range_high, 100)) == (31600, 47400)


def _worked_example_inputs(cat) -> EstimateInputs:
    """A photo laid out to match the worked example exactly (positions are arbitrary)."""
    door = box_region("door", "door", 500, 1539, 700, 2000)  # 461 x 200 px, inside the wall
    wall = region("wall", "wall", trapezoid_wall(1_050_000, 1.05, 1300, hole_px=461 * 200))
    pillar_h, pillar_w = 10 / FT, 1.2 / FT
    p1 = box_region("p1", "pillar", 1400, 2000 - pillar_h, 1400 + pillar_w, 2000)
    p2 = box_region("p2", "pillar", 1600, 2000 - pillar_h, 1600 + pillar_w, 2000)
    railing = box_region("rail", "railing", 1400, 100, 1880, 160)  # 480 px wide
    regions = [wall, door, p1, p2, railing]
    scale = resolve_scale(
        ScaleInputs(
            regions=regions,
            door_visible=0.9,
            door_box_px=BoxPx(x0=500, y0=1539, x1=700, y1=2000),
            floors_answer=2,
        )
    )
    return EstimateInputs(
        regions=regions,
        scale=scale,
        assignments=[
            Assignment(region_id="wall", material_id="paint-premium-emulsion", color="#E8D9B5"),
            Assignment(region_id="p1", material_id="cladding-natural-stone"),
            Assignment(region_id="p2", material_id="cladding-natural-stone"),
            Assignment(region_id="rail", material_id="railing-toughened-glass"),
        ],
        materials=cat,
        floors=2,
        scale_confirmed=True,
    )


def test_end_to_end_worked_example(cat):
    inputs = _worked_example_inputs(cat)
    surfaces, openings = measure_surfaces(inputs.regions, inputs.scale)
    wall = next(s for s in surfaces if s.label == "wall")
    assert wall.net_px == pytest.approx(1_050_000, rel=1e-9)
    assert wall.fs == pytest.approx(1.05, rel=1e-9)
    assert [o.region_id for o in openings] == ["door"]

    est = compute_estimate(inputs)
    assert [line.total for line in est.lines] == [6659, 12150, 11058]
    assert est.lines[1].region_ids == ["p1", "p2"]
    assert est.lines[1].measured_quantity == pytest.approx(72.0)
    assert est.category_subtotals == {"paint": 6659, "cladding": 12150, "railing": 11058}
    assert est.lines_total == 29867
    assert round(est.wall_area_sqft, 1) == 254.2
    assert est.scaffolding == 2034
    assert est.contingency == 1595
    assert est.tax == 6029
    assert round(est.grand_total) == 39525
    assert est.range_pct == 20
    assert (est.range_low, est.range_high) == (31600, 47400)
    assert est.confidence == Confidence.medium
    assert est.provisional is False
    assert len(est.fingerprint) == 64
    text = " ".join(est.assumptions)
    assert "main door" in text
    assert "Pillars" in text
    assert "Scaffolding is included" in text
