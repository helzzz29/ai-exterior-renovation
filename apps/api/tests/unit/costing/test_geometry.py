from __future__ import annotations

import math

import pytest
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon

from renocore.costing import (
    FS_CAP,
    area_from_px,
    best_fit_quad,
    foreshortening,
    measure_surfaces,
    net_geometries,
    pillar_area,
)
from renocore.costing.surfaces import (
    _polygonal_parts,
    _ratio,
    bbox,
    box_height,
    box_width,
    to_polygon,
    union_bbox,
)

from .helpers import box_region, rect, region, scale_of


def test_to_polygon_repairs_bow_tie():
    bow = [(0, 0), (10, 10), (10, 0), (0, 10)]
    geom = to_polygon(bow)
    assert geom.is_valid
    assert geom.area == pytest.approx(50)


def test_polygonal_parts_and_ratio_helpers():
    sq = Polygon(rect(0, 0, 1, 1))
    assert _polygonal_parts(sq) == [sq]
    assert _polygonal_parts(Polygon()) == []
    mixed = GeometryCollection([sq, LineString([(0, 0), (5, 5)]), MultiPolygon([sq])])
    assert len(_polygonal_parts(mixed)) == 2
    assert _ratio(2, 4) == 2 and _ratio(0, 4) is None


def test_bbox_helpers():
    assert bbox(Polygon()) is None
    assert box_width(None) == 0 and box_height(None) == 0
    assert union_bbox([]) is None


def test_opening_subtraction_is_exact():
    wall = box_region("w", "wall", 0, 0, 1000, 500)
    win = box_region("win", "window", 100, 100, 300, 250)  # 30,000 px
    door = box_region("d", "door", 500, 200, 600, 500)  # 30,000 px
    surfaces, openings = measure_surfaces([wall, win, door], scale_of(0.02))
    (w,) = surfaces
    assert w.net_px == pytest.approx(500_000 - 60_000)
    assert w.fs == 1.0
    assert w.area_sqft == pytest.approx(440_000 * 0.0004)
    assert w.length_ft == pytest.approx(20)
    assert [o.label for o in openings] == ["window", "door"]
    assert openings[0].area_sqft == pytest.approx(30_000 * 0.0004)
    assert openings[0].length_ft is None


def test_priority_resolves_overlap_both_ways():
    railing = box_region("r", "railing", 0, 0, 100, 100)
    balcony = box_region("b", "balcony", 50, 0, 150, 100)
    nets = net_geometries([balcony, railing])  # input order must not matter
    assert nets["r"].area == pytest.approx(10_000)
    assert nets["b"].area == pytest.approx(5_000)


def test_window_beats_door_and_same_label_overlap_counted_once():
    w1 = box_region("w1", "wall", 0, 0, 100, 100)
    w2 = box_region("w2", "wall", 50, 0, 150, 100)
    win = box_region("win", "window", 0, 0, 10, 10)
    door = box_region("d", "door", 0, 0, 20, 20)
    nets = net_geometries([w1, w2, win, door])
    assert nets["w1"].area == pytest.approx(10_000 - 400)
    assert nets["w2"].area == pytest.approx(5_000)
    assert nets["d"].area == pytest.approx(300)


def test_duplicate_region_ids_rejected():
    with pytest.raises(ValueError):
        measure_surfaces(
            [box_region("a", "wall", 0, 0, 1, 1), box_region("a", "gate", 0, 0, 1, 1)],
            scale_of(1),
        )


# ---------------------------------------------------------------- perspective


def test_fs_rectangle_is_one():
    assert foreshortening(rect(0, 0, 400, 300)) == 1.0


def test_fs_trapezoid():
    pts = [(0, 200), (200, 200), (200, 90), (0, 100)]  # left 100, right 110
    top = math.hypot(200, 10)
    assert foreshortening(pts) == pytest.approx(math.sqrt(1.1 * top / 200))


def test_fs_rotated_orientation_pairs():
    # start the ring on a vertical edge so the other edge pair is "vertical"
    pts = [(0, 100), (0, 200), (200, 200), (200, 90)]
    top = math.hypot(200, 10)
    assert foreshortening(pts) == pytest.approx(math.sqrt(1.1 * top / 200))


def test_fs_capped():
    pts = [(0, 1000), (100, 1000), (100, 0), (0, 900)]  # 100 vs 1000 vertical
    assert foreshortening(pts) == FS_CAP


def test_fs_triangle_and_degenerate():
    assert foreshortening([(0, 0), (10, 0), (5, 10)]) == 1.0
    assert best_fit_quad([(0, 0), (10, 0), (5, 10)]) is None
    assert foreshortening([(0, 0), (10, 0), (20, 0), (5, 0)]) == 1.0  # zero area


def test_fs_noisy_quad_simplifies_to_four_corners():
    # a trapezoid with extra nearly-collinear points along its edges
    pts = [
        (0, 200),
        (50, 200.4),
        (100, 199.7),
        (200, 200),
        (200, 150.3),
        (200, 90),
        (100, 95.2),
        (0, 100),
        (0.3, 150),
    ]
    quad = best_fit_quad(pts)
    assert quad is not None and len(quad) == 4
    assert foreshortening(pts) == pytest.approx(1.05, abs=0.01)


def test_fs_collinear_points_removed():
    pts = [(0, 0), (50, 0), (100, 0), (100, 100), (0, 100)]
    assert best_fit_quad(pts) is not None
    assert foreshortening(pts) == 1.0


def test_fs_circle_is_not_a_quad():
    circle = [
        (math.cos(t) * 100, math.sin(t) * 100) for t in [i * 2 * math.pi / 40 for i in range(40)]
    ]
    quad = best_fit_quad(circle)
    # a circle may collapse to a quad or a triangle; either way fs stays modest
    assert quad is None or len(quad) == 4
    assert 1.0 <= foreshortening(circle) <= FS_CAP


# ---------------------------------------------------------------- per label


def test_area_formulas():
    assert area_from_px(10_000, 0.1) == pytest.approx(100)
    assert area_from_px(10_000, 0.1, 1.2) == pytest.approx(120)
    assert pillar_area(10, 1.2) == pytest.approx(36)


def test_measure_every_label():
    ft = 0.1
    regions = [
        box_region("wall", "wall", 0, 0, 1000, 600),
        box_region("par", "parapet", 0, -50, 1000, 0),
        box_region("pil", "pillar", 1100, 0, 1112, 100),  # 10 ft x 1.2 ft
        box_region("bal", "balcony", 1200, 0, 1400, 100),
        box_region("rail", "railing", 1200, 50, 1400, 100),  # in front of the balcony
        region("gate", "gate", [(1500, 0), (1600, 0), (1600, 50), (1550, 80), (1500, 50)]),
        box_region("roof", "roof_edge", 0, -60, 1000, -50),
    ]
    surfaces, openings = measure_surfaces(regions, scale_of(ft))
    by = {s.region_id: s for s in surfaces}
    assert openings == []
    assert by["par"].area_sqft == pytest.approx(500)
    assert by["par"].length_ft == pytest.approx(100)
    assert by["pil"].area_sqft == pytest.approx(36)
    assert by["pil"].length_ft == pytest.approx(10)
    assert by["bal"].area_sqft == pytest.approx(100)  # railing part removed
    assert by["rail"].area_sqft == pytest.approx(100)
    assert by["rail"].length_ft == pytest.approx(20)
    assert by["gate"].area_sqft == pytest.approx(10 * 8)  # bounding box
    assert by["roof"].area_sqft == pytest.approx(100)
    assert by["roof"].length_ft == pytest.approx(100)


def test_fully_hidden_pillar_and_gate_measure_zero():
    regions = [
        box_region("win", "window", 0, 0, 100, 100),
        box_region("pil", "pillar", 10, 10, 20, 90),
        box_region("gate", "gate", 30, 30, 60, 60),
    ]
    surfaces, _ = measure_surfaces(regions, scale_of(0.1))
    assert all(s.area_sqft == 0 for s in surfaces)


def test_fs_applied_to_wall_area():
    pts = [(0, 200), (200, 200), (200, 90), (0, 100)]
    (s,), _ = measure_surfaces([region("w", "wall", pts)], scale_of(0.1))
    assert s.fs > 1.0
    assert s.area_sqft == pytest.approx(Polygon(pts).area * 0.01 * s.fs)
