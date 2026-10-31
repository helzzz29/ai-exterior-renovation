"""Pixel-space geometry: polygon repair, overlap ownership, perspective factor and
area per surface (estimation.md sections 2 and 3)."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.domain.models import (
    LABEL_PRIORITY,
    OPENING_LABELS,
    BoxPx,
    Point,
    Region,
    ScaleResult,
    SurfaceMeasure,
)

FS_CAP = 1.4
FS_LABELS: frozenset[str] = frozenset({"wall", "parapet", "balcony"})
PILLAR_EXPOSED_FACES = 3

_EMPTY = Polygon()


def to_polygon(points: Sequence[Point]) -> BaseGeometry:
    """Build a valid polygonal geometry from a point list (self-intersections repaired)."""
    poly = Polygon(points)
    if poly.is_valid:
        return poly
    fixed = make_valid(poly)
    parts = _polygonal_parts(fixed)
    if not parts:  # pragma: no cover - make_valid of a 3+ point ring always yields something
        return _EMPTY
    merged = unary_union(parts)
    return merged if merged.is_valid else merged.buffer(0)


def _polygonal_parts(geom: BaseGeometry) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if not g.is_empty]
    out: list[Polygon] = []
    for g in getattr(geom, "geoms", []):
        out.extend(_polygonal_parts(g))
    return out


def bbox(geom: BaseGeometry) -> BoxPx | None:
    """Axis-aligned bounding box in pixels, or None for an empty geometry."""
    if geom.is_empty:
        return None
    x0, y0, x1, y1 = geom.bounds
    return BoxPx(x0=x0, y0=y0, x1=x1, y1=y1)


def box_width(box: BoxPx | None) -> float:
    return 0.0 if box is None else box.x1 - box.x0


def box_height(box: BoxPx | None) -> float:
    return 0.0 if box is None else box.y1 - box.y0


def union_bbox(regions: Iterable[Region]) -> BoxPx | None:
    """Bounding box around all given regions (None when there are none)."""
    xs: list[float] = []
    ys: list[float] = []
    for r in regions:
        for x, y in r.polygon:
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    return BoxPx(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))


def net_geometries(regions: Sequence[Region]) -> dict[str, BaseGeometry]:
    """Each pixel belongs to at most one region.

    A region keeps only the part not covered by any region of a higher-priority label
    (``LABEL_PRIORITY``, earlier wins) or by an earlier region of the same label.
    Regions proposed from a decision-model bounding box (source ``jev_box``) are coarse
    rectangles that only mark where a railing or gate is; they never take pixels from others.
    """
    rank = {label: i for i, label in enumerate(LABEL_PRIORITY)}
    ordered = sorted(enumerate(regions), key=lambda t: (rank[t[1].label], t[0]))
    taken: BaseGeometry = _EMPTY
    out: dict[str, BaseGeometry] = {}
    for _, region in ordered:
        geom = to_polygon(region.polygon)
        net = geom if taken.is_empty else geom.difference(taken)
        out[region.id] = net
        if region.source == "jev_box":
            continue
        taken = unary_union([taken, geom]) if not taken.is_empty else geom
    return out


# ---------------------------------------------------------------- perspective factor


def best_fit_quad(points: Sequence[Point]) -> list[Point] | None:
    """Simplify a polygon to four corners, or None when it does not reduce to four.

    Tolerance grows geometrically (relative to the polygon's size) until the ring has at
    most four corners.
    """
    poly = to_polygon(points)
    if not isinstance(poly, Polygon) or poly.is_empty:
        return None
    ring = _corners(poly)
    if len(ring) == 4:
        return ring
    if len(ring) < 4:
        return None
    x0, y0, x1, y1 = poly.bounds
    diag = math.hypot(x1 - x0, y1 - y0)
    tol = diag * 0.002
    while tol < diag:
        simple = poly.simplify(tol, preserve_topology=True)
        ring = _corners(simple) if isinstance(simple, Polygon) else []
        if len(ring) <= 4:
            return ring if len(ring) == 4 else None
        tol *= 1.5
    return None  # pragma: no cover - a ring always collapses before tol reaches diag


def _corners(poly: Polygon) -> list[Point]:
    """Exterior ring corners without the closing point and without collinear vertices."""
    coords = list(poly.exterior.coords)[:-1]
    out: list[Point] = []
    n = len(coords)
    for i in range(n):
        ax, ay = coords[i - 1]
        bx, by = coords[i]
        cx, cy = coords[(i + 1) % n]
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        scale = max(math.hypot(bx - ax, by - ay) * math.hypot(cx - bx, cy - by), 1e-12)
        if abs(cross) / scale > 1e-9:
            out.append((float(bx), float(by)))
    return out


def foreshortening(points: Sequence[Point]) -> float:
    """Perspective factor fs = min(sqrt(fs_v * fs_h), 1.4); 1.0 if not a quadrilateral."""
    quad = best_fit_quad(points)
    if quad is None:
        return 1.0
    edges = [(quad[i], quad[(i + 1) % 4]) for i in range(4)]
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in edges]
    # Opposite edges pair up: (0, 2) and (1, 3). The pair that is more upright is "vertical".
    verticalness = [abs(b[1] - a[1]) / max(lengths[i], 1e-12) for i, (a, b) in enumerate(edges)]
    pair_a, pair_b = (0, 2), (1, 3)
    if verticalness[0] + verticalness[2] >= verticalness[1] + verticalness[3]:
        vert, horiz = pair_a, pair_b
    else:
        vert, horiz = pair_b, pair_a
    fs_v = _ratio(lengths[vert[0]], lengths[vert[1]])
    fs_h = _ratio(lengths[horiz[0]], lengths[horiz[1]])
    if fs_v is None or fs_h is None:  # pragma: no cover - corners never coincide
        return 1.0
    return min(math.sqrt(fs_v * fs_h), FS_CAP)


def _ratio(a: float, b: float) -> float | None:
    lo, hi = min(a, b), max(a, b)
    if lo <= 0:
        return None
    return hi / lo


# ---------------------------------------------------------------- areas


def area_from_px(net_px: float, ft_per_px: float, fs: float = 1.0) -> float:
    """area_sqft = net_pixels x ft_per_px^2 x fs."""
    return net_px * ft_per_px * ft_per_px * fs


def length_from_px(length_px: float, ft_per_px: float) -> float:
    """length_ft = length_px x ft_per_px."""
    return length_px * ft_per_px


def pillar_area(height_ft: float, width_ft: float) -> float:
    """Square column assumed, three faces exposed: height x 3 x width."""
    return height_ft * PILLAR_EXPOSED_FACES * width_ft


def measure_region(region: Region, net: BaseGeometry, ft_per_px: float) -> SurfaceMeasure:
    """Measured quantity for one region given its net (ownership-resolved) geometry."""
    own_box = bbox(to_polygon(region.polygon))
    w_ft = length_from_px(box_width(own_box), ft_per_px)
    h_ft = length_from_px(box_height(own_box), ft_per_px)
    net_px = float(net.area)
    fs = 1.0
    length: float | None = None
    label = region.label
    if label in FS_LABELS:
        fs = foreshortening(region.polygon)
        area = area_from_px(net_px, ft_per_px, fs)
        length = w_ft
    elif label == "pillar":
        # visible front face x 3 (square column, front + two sides); equals height x 3 x width
        # for an upright rectangle, and avoids bounding-box inflation on slanted outlines
        area = PILLAR_EXPOSED_FACES * area_from_px(net_px, ft_per_px)
        length = h_ft
    elif label == "gate":
        area = w_ft * h_ft if net_px > 0 else 0.0
        length = w_ft
    else:  # railing, roof_edge, window, door
        area = area_from_px(net_px, ft_per_px)
        length = w_ft
    if label in OPENING_LABELS:
        length = None
    return SurfaceMeasure(
        region_id=region.id, label=label, net_px=net_px, fs=fs, area_sqft=area, length_ft=length
    )


def measure_surfaces(
    regions: list[Region], scale: ScaleResult
) -> tuple[list[SurfaceMeasure], list[SurfaceMeasure]]:
    """Return (priced surfaces, openings) in input order."""
    ids = [r.id for r in regions]
    if len(set(ids)) != len(ids):
        raise ValueError("region ids must be unique")
    nets = net_geometries(regions)
    surfaces: list[SurfaceMeasure] = []
    openings: list[SurfaceMeasure] = []
    for region in regions:
        m = measure_region(region, nets[region.id], scale.ft_per_px)
        (openings if region.label in OPENING_LABELS else surfaces).append(m)
    return surfaces, openings
