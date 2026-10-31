import numpy as np
import pytest

from app.domain.models import BoxFraction, BoxPx
from app.imaging import (
    box_area,
    box_iou,
    box_polygon,
    fraction_box_to_px,
    polygon_area_px,
    polygon_box,
    polygons_mask,
)


def test_fraction_box_to_px() -> None:
    box = fraction_box_to_px(BoxFraction(top=0.1, bottom=0.5, left=0.25, right=0.75), 800, 600)
    assert box == BoxPx(x0=200, y0=60, x1=600, y1=300)


def test_fraction_box_to_px_clamps_and_orders() -> None:
    box = fraction_box_to_px(BoxFraction(top=1.2, bottom=-0.1, left=0.9, right=0.1), 100, 50)
    assert box == BoxPx(x0=10, y0=0, x1=90, y1=50)


def test_polygon_box_and_box_polygon() -> None:
    poly = [(10.0, 20.0), (50.0, 5.0), (30.0, 60.0)]
    assert polygon_box(poly) == BoxPx(x0=10, y0=5, x1=50, y1=60)
    corners = box_polygon(BoxPx(x0=1, y0=2, x1=3, y1=4))
    assert corners == [(1, 2), (3, 2), (3, 4), (1, 4)]
    with pytest.raises(ValueError):
        polygon_box([])


def test_box_iou_cases() -> None:
    a = BoxPx(x0=0, y0=0, x1=10, y1=10)
    assert box_iou(a, a) == pytest.approx(1.0)
    assert box_iou(a, BoxPx(x0=5, y0=0, x1=15, y1=10)) == pytest.approx(50 / 150)
    assert box_iou(a, BoxPx(x0=10, y0=0, x1=20, y1=10)) == 0.0  # touching edges
    assert box_iou(a, BoxPx(x0=20, y0=20, x1=30, y1=30)) == 0.0  # disjoint
    assert box_iou(a, BoxPx(x0=2, y0=2, x1=4, y1=4)) == pytest.approx(4 / 100)  # contained
    zero = BoxPx(x0=5, y0=5, x1=5, y1=5)
    assert box_iou(zero, zero) == 0.0
    assert box_area(BoxPx(x0=5, y0=5, x1=1, y1=9)) == 0.0


def test_polygon_area_and_mask() -> None:
    sq = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert polygon_area_px(sq) == pytest.approx(100.0)
    assert polygon_area_px(sq[:2]) == 0.0
    mask = polygons_mask((20, 15), [sq, [(1.0, 1.0), (2.0, 2.0)]])
    assert mask.shape == (15, 20) and mask.dtype == np.uint8
    assert mask[5, 5] == 255 and mask[12, 15] == 0
    assert polygons_mask((5, 5), []).sum() == 0
