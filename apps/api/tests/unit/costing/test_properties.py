"""Property-based tests (Hypothesis, derandomized for reproducible CI runs)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from renocore.costing import (
    DEFAULT_CATALOGUE_PATH,
    compute_estimate,
    load_catalogue,
    material_quantity,
    measure_surfaces,
    price_line,
    with_wastage,
)
from renocore.schemas.entities import Assignment, EstimateInputs

from .helpers import box_region, scale_of

CAT = load_catalogue(DEFAULT_CATALOGUE_PATH)
AREA_MATERIALS = [m for m in CAT.values() if m.measure_basis == "area"]
PROFILE = settings(derandomize=True, max_examples=150, deadline=None)

sizes = st.floats(min_value=1, max_value=2000, allow_nan=False)
scales = st.floats(min_value=0.001, max_value=0.2, allow_nan=False)
areas = st.floats(min_value=0, max_value=20_000, allow_nan=False)


@PROFILE
@given(w=sizes, h=sizes, ft=scales, k=st.floats(min_value=0.1, max_value=10))
def test_area_scales_with_ft_per_px_squared(w, h, ft, k):
    regions = [box_region("w", "wall", 0, 0, w, h), box_region("r", "railing", 0, -10, w, 0)]
    a, _ = measure_surfaces(regions, scale_of(ft))
    b, _ = measure_surfaces(regions, scale_of(ft * k))
    assert b[0].area_sqft == pytest.approx(a[0].area_sqft * k * k, rel=1e-9)
    assert b[1].length_ft == pytest.approx(a[1].length_ft * k, rel=1e-9)


@PROFILE
@given(material=st.sampled_from(list(CAT.values())), measured=areas)
def test_purchase_never_below_need(material, measured):
    unit = "rft" if material.measure_basis == "length" else "sqft"
    ww = with_wastage(measured, material.wastage_pct)
    q = material_quantity(material, ww, unit)
    assert q.purchase >= q.required * (1 - 1e-9)
    assert ww >= measured
    line = price_line(material, "wall", ["w"], measured)
    for c in line.companions:
        assert c.purchase_quantity >= c.quantity * (1 - 1e-9)


@PROFILE
@given(material=st.sampled_from(list(CAT.values())), a=areas, extra=areas)
def test_line_total_non_decreasing_with_area(material, a, extra):
    small = price_line(material, "wall", ["w"], a)
    big = price_line(material, "wall", ["w"], a + extra)
    assert big.total >= small.total
    assert big.purchase_quantity >= small.purchase_quantity


@PROFILE
@given(
    material=st.sampled_from(AREA_MATERIALS),
    w=st.floats(min_value=10, max_value=1500),
    grow=st.floats(min_value=0, max_value=500),
    floors=st.integers(min_value=1, max_value=4),
)
def test_grand_total_non_decreasing_with_wall_size(material, w, grow, floors):
    def total(width: float) -> float:
        est = compute_estimate(
            EstimateInputs(
                regions=[box_region("w", "wall", 0, 0, width, 400)],
                scale=scale_of(0.02),
                assignments=[Assignment(region_id="w", material_id=material.id)],
                materials=CAT,
                floors=floors,
            )
        )
        assert est.range_low - 50 <= est.grand_total <= est.range_high + 50
        return est.grand_total

    assert total(w + grow) >= total(w)
