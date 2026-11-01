"""Rules added after live runs on real photos."""

import pytest

from renocore.costing import measure_surfaces
from tests.unit.costing.helpers import box_region, region, scale_of


def by_id(surfaces):
    return {s.region_id: s for s in surfaces}


def test_jev_box_proposal_does_not_take_wall_area():
    wall = box_region("w", "wall", 0, 0, 100, 100)
    proposal = box_region("r", "railing", 0, 0, 100, 50).model_copy(update={"source": "jev_box"})
    surfaces, _ = measure_surfaces([wall, proposal], scale_of(0.1))
    got = by_id(surfaces)
    assert got["w"].area_sqft == pytest.approx(100.0)  # 100x100 px at 0.1 ft/px, untouched
    assert got["r"].length_ft == pytest.approx(10.0)  # still measured by running length


def test_traced_railing_still_takes_wall_area():
    wall = box_region("w", "wall", 0, 0, 100, 100)
    railing = box_region("r", "railing", 0, 0, 100, 50)  # traced (gemini/user) outline
    surfaces, _ = measure_surfaces([wall, railing], scale_of(0.1))
    assert by_id(surfaces)["w"].area_sqft == pytest.approx(50.0)


def test_pillar_uses_visible_face_not_bounding_box():
    # a slanted pillar outline: its bounding box (40 x 200) is twice its face area
    slanted = region("p", "pillar", [(0, 0), (20, 0), (40, 200), (20, 200)])
    upright = box_region("q", "pillar", 100, 0, 120, 200)
    surfaces, _ = measure_surfaces([slanted, upright], scale_of(0.1))
    got = by_id(surfaces)
    assert got["p"].area_sqft == pytest.approx(3 * 4000 * 0.01)  # 3 x face area (4000 px)
    assert got["q"].area_sqft == pytest.approx(20 * 3 * 2)  # height 20 ft x 3 x width 2 ft
