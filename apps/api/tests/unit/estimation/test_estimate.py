"""End-to-end compute_estimate with simple rectangles."""

from __future__ import annotations

import pytest

from app.domain.models import (
    Assignment,
    Confidence,
    EstimateInputs,
    Extras,
    RateOverride,
    ScaleMethod,
)
from app.estimation import apply_extras, compute_estimate

from .helpers import box_region, make_material, paint_material, scale_of

FT = 0.02  # 50 px per foot -> 2500 px per sq ft


def house():
    """1000 x 500 px wall (200 sq ft gross) with a window and a door inside it."""
    return [
        box_region("wall", "wall", 0, 0, 1000, 500),
        box_region("win", "window", 100, 100, 300, 225),  # 25,000 px = 10 sq ft
        box_region("door", "door", 500, 250, 625, 500),  # 31,250 px = 12.5 sq ft
        box_region("rail", "railing", 1100, 0, 1600, 50),  # 10 ft long
        box_region("gate", "gate", 1700, 250, 2200, 500),  # 10 x 5 ft
    ]


def materials():
    return {
        "paint": paint_material(),
        "rail": make_material(
            id="rail",
            category="railing",
            pricing_unit="rft",
            measure_basis="length",
            wastage_pct=5,
            material_rate=1000,
            labour_rate=100,
            applicable_labels=["railing"],
        ),
        "gate": make_material(
            id="gate",
            category="gate",
            pricing_unit="sqft",
            wastage_pct=5,
            material_rate=400,
            labour_rate=50,
            applicable_labels=["gate"],
        ),
    }


def inputs(**kw) -> EstimateInputs:
    args = {
        "regions": house(),
        "scale": scale_of(FT),
        "assignments": [
            Assignment(region_id="wall", material_id="paint"),
            Assignment(region_id="rail", material_id="rail"),
            Assignment(region_id="gate", material_id="gate"),
        ],
        "materials": materials(),
        "floors": 1,
        "scale_confirmed": True,
    }
    args.update(kw)
    return EstimateInputs(**args)


def test_single_floor_estimate():
    est = compute_estimate(inputs())
    wall, rail, gate = est.lines
    assert wall.measured_quantity == pytest.approx(200 - 10 - 12.5)  # exact subtraction
    assert est.wall_area_sqft == pytest.approx(177.5)
    # paint: 177.5 x 2 / 100 = 3.55 L -> 1 can; primer 1.775 L -> 1 can
    assert (wall.packs, wall.purchase_quantity, wall.material_cost) == (1, 4, 1600)
    assert wall.companions[0].cost == 1000
    assert wall.labour_cost == 1775
    assert wall.total == 4375
    # railing: 10 rft + 5% = 10.5 -> 11 rft
    assert (rail.measured_quantity, rail.purchase_quantity, rail.total) == (
        pytest.approx(10),
        11,
        11000 + 1000,
    )
    # gate: 50 sqft + 5% = 52.5 -> 53 sqft
    assert (gate.purchase_quantity, gate.total) == (53, 53 * 400 + 50 * 50)
    assert est.scaffolding == 0
    lines = 4375 + 12000 + 23700
    assert est.lines_total == lines
    assert est.contingency == round(lines * 0.05)
    assert est.tax == round((lines + est.contingency) * 0.18)
    assert est.grand_total == lines + est.contingency + est.tax
    assert est.range_pct == 10 and est.confidence == Confidence.high
    assert est.category_subtotals == {"paint": 4375, "railing": 12000, "gate": 23700}
    assert [o.region_id for o in est.openings] == ["win", "door"]
    assert not any("Scaffolding" in a for a in est.assumptions)


def test_two_floors_adds_scaffolding():
    est = compute_estimate(inputs(floors=2))
    assert est.scaffolding == round(177.5 * 8)
    assert est.contingency == round((est.lines_total + est.scaffolding) * 0.05)
    assert any(
        "Scaffolding is included because the house has 2 floors" in a for a in est.assumptions
    )


def test_scaffolding_threshold_and_rate_editable():
    ex = Extras(scaffolding_rate_per_sqft=10, scaffolding_min_floors=3)
    assert compute_estimate(inputs(floors=2, extras=ex)).scaffolding == 0
    assert compute_estimate(inputs(floors=3, extras=ex)).scaffolding == 1775


def test_extras_edit_contingency_and_tax():
    est = compute_estimate(inputs(extras=Extras(contingency_pct=0, tax_pct=0)))
    assert est.contingency == 0 and est.tax == 0
    assert est.grand_total == est.lines_total


def test_overrides_apply_and_flag():
    est = compute_estimate(
        inputs(
            overrides=[
                RateOverride(material_id="gate", material_rate=1),
                RateOverride(material_id="gate", material_rate=300),  # last wins
                RateOverride(material_id="rail", labour_rate=0),
            ]
        )
    )
    wall, rail, gate = est.lines
    assert gate.material_rate == 300 and gate.rate_overridden
    assert rail.labour_cost == 0 and rail.rate_overridden
    assert not wall.rate_overridden
    assert any("Prices you changed" in a for a in est.assumptions)


def test_grouping_by_material_and_label():
    regions = [
        box_region("w1", "wall", 0, 0, 500, 500),
        box_region("w2", "wall", 600, 0, 1100, 500),
        box_region("p1", "parapet", 0, -50, 1100, 0),
    ]
    est = compute_estimate(
        inputs(
            regions=regions,
            assignments=[
                Assignment(region_id="w1", material_id="paint"),
                Assignment(region_id="p1", material_id="paint"),
                Assignment(region_id="w2", material_id="paint"),
            ],
        )
    )
    assert [(line.label, line.region_ids) for line in est.lines] == [
        ("wall", ["w1", "w2"]),
        ("parapet", ["p1"]),
    ]
    assert est.lines[0].measured_quantity == pytest.approx(200)
    assert est.category_subtotals == {"paint": est.lines[0].total + est.lines[1].total}


def test_reassignment_last_wins_and_openings_not_priced():
    est = compute_estimate(
        inputs(
            assignments=[
                Assignment(region_id="gate", material_id="paint"),
                Assignment(region_id="gate", material_id="gate"),
                Assignment(region_id="win", material_id="paint"),
            ]
        )
    )
    assert [line.material_id for line in est.lines] == ["gate"]
    assert any("windows or doors are not priced" in a for a in est.assumptions)
    assert est.wall_area_sqft == 0


def test_length_priced_material_on_wall_uses_running_length():
    est = compute_estimate(inputs(assignments=[Assignment(region_id="wall", material_id="rail")]))
    assert est.lines[0].measured_quantity == pytest.approx(20)
    assert est.wall_area_sqft == 0  # wall area only counts area-priced wall lines


def test_unknown_ids_raise():
    with pytest.raises(ValueError, match="unknown region"):
        compute_estimate(inputs(assignments=[Assignment(region_id="x", material_id="paint")]))
    with pytest.raises(ValueError, match="unknown material"):
        compute_estimate(inputs(assignments=[Assignment(region_id="wall", material_id="x")]))


def test_empty_estimate():
    est = compute_estimate(inputs(assignments=[]))
    assert est.lines == [] and est.grand_total == 0 and est.range_low == 0
    assert est.category_subtotals == {}


def test_tiny_and_zero_areas():
    regions = [box_region("wall", "wall", 0, 0, 1, 1), box_region("gate", "gate", 0, 0, 1, 1)]
    regions.append(box_region("win", "window", 0, 0, 1, 1))  # hides both completely
    est = compute_estimate(
        inputs(
            regions=regions,
            assignments=[
                Assignment(region_id="wall", material_id="paint"),
                Assignment(region_id="gate", material_id="gate"),
            ],
        )
    )
    assert all(line.total == 0 for line in est.lines)
    tiny = compute_estimate(
        inputs(
            regions=[box_region("wall", "wall", 0, 0, 2, 2)],
            assignments=[Assignment(region_id="wall", material_id="paint")],
        )
    )
    line = tiny.lines[0]
    assert line.packs == 1 and line.purchase_quantity == 4  # one can even for a tiny patch
    assert line.companions[0].packs == 1


def test_provisional_and_ranges_by_confidence():
    low = scale_of(FT, Confidence.low, ScaleMethod.floors)
    est = compute_estimate(inputs(scale=low, scale_confirmed=False))
    assert est.provisional and est.range_pct == 35
    assert any("first estimate" in a for a in est.assumptions)
    assert any("Each floor" in a for a in est.assumptions)
    med = scale_of(FT, Confidence.medium, ScaleMethod.windows)
    est = compute_estimate(inputs(scale=med))
    assert est.range_pct == 20
    assert any("standard window" in a for a in est.assumptions)


def test_angled_wall_assumption_and_companion_note():
    regions = [box_region("x", "pillar", 0, 0, 10, 10)]
    regions.append(
        box_region("wall", "wall", 0, 0, 10, 10).model_copy(
            update={"polygon": [(0, 200), (200, 200), (200, 90), (0, 100)]}
        )
    )
    est = compute_estimate(
        inputs(
            regions=regions,
            assignments=[
                Assignment(region_id="wall", material_id="paint"),
                Assignment(region_id="x", material_id="gate"),
            ],
        )
    )
    text = " ".join(est.assumptions)
    assert "photographed at an angle" in text
    assert "Primer for paint" in text
    assert "Pillars are taken as square" in text


def test_apply_extras_direct():
    t = apply_extras(1000, 100, 2, Extras(), Confidence.low)
    assert (t.scaffolding, t.contingency, t.tax) == (800, 90, 340)
    assert t.grand_total == 2230
    assert (t.range_low, t.range_high) == (1400, 3000)
