"""Box and polygon helpers plus polygon rasterisation."""

from collections.abc import Sequence

import cv2
import numpy as np
from shapely.geometry import Polygon

from app.domain.models import BoxFraction, BoxPx, Point


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def fraction_box_to_px(box: BoxFraction, width: int, height: int) -> BoxPx:
    """Convert a fractional (0-1) box to pixels, clamped to the image and ordered."""
    xs = sorted((box.left * width, box.right * width))
    ys = sorted((box.top * height, box.bottom * height))
    return BoxPx(
        x0=_clamp(xs[0], 0, width),
        y0=_clamp(ys[0], 0, height),
        x1=_clamp(xs[1], 0, width),
        y1=_clamp(ys[1], 0, height),
    )


def polygon_box(polygon: list[Point]) -> BoxPx:
    """Axis-aligned bounding box of a polygon."""
    if not polygon:
        raise ValueError("polygon has no points")
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return BoxPx(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))


def box_polygon(box: BoxPx) -> list[Point]:
    """Four corners clockwise (in image coordinates) from the top-left."""
    return [(box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1)]


def box_area(box: BoxPx) -> float:
    return max(0.0, box.x1 - box.x0) * max(0.0, box.y1 - box.y0)


def box_iou(a: BoxPx, b: BoxPx) -> float:
    """Intersection over union; 0.0 when the union is empty."""
    iw = min(a.x1, b.x1) - max(a.x0, b.x0)
    ih = min(a.y1, b.y1) - max(a.y0, b.y0)
    inter = max(0.0, iw) * max(0.0, ih)
    union = box_area(a) + box_area(b) - inter
    if union <= 0:
        return 0.0
    return inter / union


def polygon_area_px(polygon: Sequence[Point]) -> float:
    """Geometric (shoelace) area of a polygon in square pixels."""
    if len(polygon) < 3:
        return 0.0
    return float(Polygon(polygon).area)


def _to_int_points(polygon: Sequence[Point]) -> np.ndarray:
    return np.round(np.asarray(polygon, dtype=np.float64)).astype(np.int32).reshape(-1, 1, 2)


def fill_polygons(canvas: np.ndarray, polygons: Sequence[Sequence[Point]], value) -> None:
    """Fill polygons in place on `canvas` (no anti-aliasing)."""
    pts = [_to_int_points(p) for p in polygons if len(p) >= 3]
    if pts:
        cv2.fillPoly(canvas, pts, value, lineType=cv2.LINE_8)


def polygons_mask(size: tuple[int, int], polygons: Sequence[Sequence[Point]]) -> np.ndarray:
    """Rasterise polygons into a uint8 mask (255 inside, 0 outside). `size` is (width, height)."""
    width, height = size
    mask = np.zeros((height, width), dtype=np.uint8)
    fill_polygons(mask, polygons, 255)
    return mask
