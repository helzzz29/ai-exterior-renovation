from __future__ import annotations

import math

import pytest

from renocore.costing import (
    resolve_scale,
    scale_from_door,
    scale_from_floors,
    scale_from_measurement,
    scale_from_windows,
    silhouette,
)
from renocore.costing.calibration import explain, geometric_mean
from renocore.schemas.entities import (
    BoxPx,
    Confidence,
    Measurements,
    ReferenceLine,
    ScaleInputs,
    ScaleMethod,
)

from .helpers import box_region

WALL = box_region("w", "wall", 0, 100, 1000, 700)  # 1000 x 600 px
PARAPET = box_region("pp", "parapet", 0, 50, 1000, 100)  # silhouette 1000 x 650
DOOR_BOX = BoxPx(x0=400, y0=490, x1=500, y1=700)  # 210 px tall


def door_region(h: float = 210):
    return box_region("d", "door", 400, 700 - h, 500, 700)


def windows(*heights: float):
    return [
        box_region(f"win{i}", "window", 100 + i * 150, 200, 200 + i * 150, 200 + h)
        for i, h in enumerate(heights)
    ]


# ---------------------------------------------------------------- silhouette


def test_silhouette_uses_wall_and_parapet_only():
    gate = box_region("g", "gate", -500, 0, -100, 900)
    sil = silhouette([WALL, PARAPET, gate])
    assert (sil.x0, sil.y0, sil.x1, sil.y1) == (0, 50, 1000, 700)


def test_silhouette_falls_back_to_all_regions():
    sil = silhouette([box_region("g", "gate", 10, 20, 30, 60)])
    assert (sil.x0, sil.y0, sil.x1, sil.y1) == (10, 20, 30, 60)
    assert silhouette([]) is None


# ---------------------------------------------------------------- priority 1


def test_user_width_measurement_high():
    s = resolve_scale(ScaleInputs(regions=[WALL], measurements=Measurements(facade_width_ft=30)))
    assert s.method == ScaleMethod.user_measurement
    assert s.confidence == Confidence.high
    assert s.ft_per_px == pytest.approx(0.03)
    assert s.facade_width_ft == pytest.approx(30)
    assert s.needs_measurement is False
    assert s.explanation.startswith("We used the measurement you gave us.")
    assert "about 30 ft wide" in s.explanation


def test_user_height_measurement():
    s = resolve_scale(ScaleInputs(regions=[WALL], measurements=Measurements(facade_height_ft=18)))
    assert s.ft_per_px == pytest.approx(18 / 600)


def test_user_reference_line():
    line = ReferenceLine(x1=0, y1=0, x2=300, y2=400, length_ft=10)  # 500 px
    s = resolve_scale(ScaleInputs(regions=[WALL], measurements=Measurements(reference_line=line)))
    assert s.ft_per_px == pytest.approx(0.02)


def test_user_measurements_geometric_mean():
    m = Measurements(facade_width_ft=30, facade_height_ft=24)  # 0.03 and 0.04
    s = resolve_scale(ScaleInputs(regions=[WALL], measurements=m))
    assert s.ft_per_px == pytest.approx(math.sqrt(0.03 * 0.04))
    line = ReferenceLine(x1=0, y1=0, x2=0, y2=100, length_ft=5)  # 0.05
    m3 = Measurements(facade_width_ft=30, facade_height_ft=24, reference_line=line)
    assert scale_from_measurement(
        ScaleInputs(regions=[WALL], measurements=m3), silhouette([WALL])
    ) == pytest.approx((0.03 * 0.04 * 0.05) ** (1 / 3))


def test_user_measurement_beats_door():
    s = resolve_scale(
        ScaleInputs(
            regions=[WALL, door_region()],
            measurements=Measurements(facade_width_ft=40),
            door_visible=0.99,
            door_box_px=DOOR_BOX,
        )
    )
    assert s.method == ScaleMethod.user_measurement


def test_zero_length_reference_line_ignored():
    line = ReferenceLine(x1=5, y1=5, x2=5, y2=5, length_ft=10)
    inputs = ScaleInputs(regions=[WALL], measurements=Measurements(reference_line=line))
    assert scale_from_measurement(inputs, silhouette([WALL])) is None
    assert resolve_scale(inputs).method == ScaleMethod.floors


def test_width_without_regions_ignored_but_line_works():
    line = ReferenceLine(x1=0, y1=0, x2=100, y2=0, length_ft=5)
    s = resolve_scale(
        ScaleInputs(regions=[], measurements=Measurements(facade_width_ft=30, reference_line=line))
    )
    assert s.ft_per_px == pytest.approx(0.05)
    assert s.facade_width_ft is None
    assert "wide" not in s.explanation


def test_photo_warned_caps_high_at_medium():
    s = resolve_scale(
        ScaleInputs(
            regions=[WALL], measurements=Measurements(facade_width_ft=30), photo_warned=True
        )
    )
    assert s.confidence == Confidence.medium
    assert s.method == ScaleMethod.user_measurement


# ---------------------------------------------------------------- priority 2


def test_door_agreeing_is_medium():
    s = resolve_scale(
        ScaleInputs(regions=[WALL, door_region(200)], door_visible=0.8, door_box_px=DOOR_BOX)
    )
    assert s.method == ScaleMethod.door
    assert s.confidence == Confidence.medium
    assert s.ft_per_px == pytest.approx(7 / 210)
    assert s.reference_box_px == DOOR_BOX
    assert s.facade_width_ft == pytest.approx(1000 * 7 / 210)
    assert s.explanation.startswith(
        "We used your main door as a guide (standard height 7 ft). That makes your house about "
        "33 ft wide."
    )


def test_door_agreement_boundary_10_percent():
    assert (
        scale_from_door(
            ScaleInputs(regions=[door_region(231)], door_visible=1, door_box_px=DOOR_BOX)
        )[1]
        == Confidence.medium
    )  # exactly +10%
    assert (
        scale_from_door(
            ScaleInputs(regions=[door_region(232)], door_visible=1, door_box_px=DOOR_BOX)
        )[1]
        == Confidence.low
    )


def test_door_disagreeing_is_low():
    s = resolve_scale(
        ScaleInputs(regions=[WALL, door_region(120)], door_visible=0.9, door_box_px=DOOR_BOX)
    )
    assert s.method == ScaleMethod.door
    assert s.confidence == Confidence.low
    assert s.needs_measurement is True
    assert "rough guess" in s.explanation


def test_door_without_region_is_low():
    s = resolve_scale(ScaleInputs(regions=[WALL], door_visible=0.9, door_box_px=DOOR_BOX))
    assert (s.method, s.confidence) == (ScaleMethod.door, Confidence.low)


def test_door_not_visible_enough_or_missing():
    regions = [WALL, door_region()]
    assert (
        scale_from_door(ScaleInputs(regions=regions, door_visible=0.69, door_box_px=DOOR_BOX))
        is None
    )
    assert scale_from_door(ScaleInputs(regions=regions, door_visible=0.9)) is None
    assert scale_from_door(ScaleInputs(regions=regions, door_box_px=DOOR_BOX)) is None
    flat = BoxPx(x0=0, y0=10, x1=10, y1=10)
    assert scale_from_door(ScaleInputs(regions=regions, door_visible=1, door_box_px=flat)) is None


def test_low_door_loses_to_medium_windows():
    regions = [WALL, door_region(100), *windows(120, 125)]
    s = resolve_scale(ScaleInputs(regions=regions, door_visible=0.9, door_box_px=DOOR_BOX))
    assert s.method == ScaleMethod.windows
    assert s.confidence == Confidence.medium
    assert s.ft_per_px == pytest.approx(4 / 122.5)


def test_medium_door_beats_windows():
    regions = [WALL, door_region(), *windows(120, 125)]
    s = resolve_scale(ScaleInputs(regions=regions, door_visible=0.9, door_box_px=DOOR_BOX))
    assert s.method == ScaleMethod.door


def test_low_door_used_when_windows_fail():
    regions = [WALL, *windows(100, 200)]
    s = resolve_scale(ScaleInputs(regions=regions, door_visible=0.9, door_box_px=DOOR_BOX))
    assert (s.method, s.confidence) == (ScaleMethod.door, Confidence.low)


# ---------------------------------------------------------------- priority 3


def test_windows_median_and_reference():
    regions = [WALL, *windows(100, 110, 105)]
    s = resolve_scale(ScaleInputs(regions=regions))
    assert s.method == ScaleMethod.windows
    assert s.ft_per_px == pytest.approx(4 / 105)
    assert s.reference_box_px.y1 - s.reference_box_px.y0 == 105
    assert "windows as a guide (standard height 4 ft)" in s.explanation


def test_windows_spread_boundary():
    assert scale_from_windows(ScaleInputs(regions=windows(100, 114.9))) is not None
    assert scale_from_windows(ScaleInputs(regions=windows(100, 115))) is None
    assert scale_from_windows(ScaleInputs(regions=windows(100))) is None


def test_windows_photo_warned_stays_medium():
    s = resolve_scale(ScaleInputs(regions=[WALL, *windows(100, 100)], photo_warned=True))
    assert s.confidence == Confidence.medium


# ---------------------------------------------------------------- priority 4


def test_floors_from_measurement_then_answer_then_one():
    sil_h = 650
    base = [WALL, PARAPET]
    s = resolve_scale(
        ScaleInputs(regions=base, measurements=Measurements(floors=3), floors_answer=2)
    )
    assert s.ft_per_px == pytest.approx(30 / sil_h)
    assert (s.method, s.confidence, s.needs_measurement) == (
        ScaleMethod.floors,
        Confidence.low,
        True,
    )
    assert "3 floors, about 10 ft each" in s.explanation
    s2 = resolve_scale(ScaleInputs(regions=base, floors_answer=2))
    assert s2.ft_per_px == pytest.approx(20 / sil_h)
    s1 = resolve_scale(ScaleInputs(regions=base))
    assert s1.ft_per_px == pytest.approx(10 / sil_h)
    assert "1 floor," in s1.explanation


def test_floors_without_regions_fails():
    assert scale_from_floors(ScaleInputs(regions=[]), None) is None
    with pytest.raises(ValueError):
        resolve_scale(ScaleInputs(regions=[]))


# ---------------------------------------------------------------- helpers


def test_geometric_mean_and_explain_small_width():
    assert geometric_mean([2, 8]) == pytest.approx(4)
    text = explain(ScaleMethod.user_measurement, Confidence.high, 8.25, 1)
    assert "about 8.2 ft wide" in text or "about 8.3 ft wide" in text
    assert "about 8 ft wide" in explain(ScaleMethod.user_measurement, Confidence.high, 8.0, 1)
