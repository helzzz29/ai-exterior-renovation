"""Gemini mask decoding (C2 post-processing) and overlap resolution by label priority."""

import base64
import binascii
import io
import logging

import cv2
import numpy as np
from PIL import Image as PILImage
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.polygon import orient

from renocore.schemas.entities import LABEL_PRIORITY, BoxPx, Point, SegmentCandidate
from renocore.schemas.vision_io import GeminiSegment

logger = logging.getLogger(__name__)

MASK_THRESHOLD = 127
MIN_COMPONENT_FRACTION = 0.002  # 0.2% of the image area
SIMPLIFY_EPSILON_FRACTION = 0.005  # 0.5% of the contour perimeter
OPEN_KERNEL = np.ones((3, 3), dtype=np.uint8)


class _MaskError(ValueError):
    pass


def _box_to_px(box_2d: list[int], width: int, height: int) -> tuple[int, int, int, int] | None:
    if len(box_2d) != 4:
        return None
    try:
        y0, x0, y1, x1 = (float(v) for v in box_2d)
    except (TypeError, ValueError):
        return None
    y0, y1 = sorted((y0, y1))
    x0, x1 = sorted((x0, x1))
    px0 = int(np.clip(round(x0 / 1000 * width), 0, width))
    px1 = int(np.clip(round(x1 / 1000 * width), 0, width))
    py0 = int(np.clip(round(y0 / 1000 * height), 0, height))
    py1 = int(np.clip(round(y1 / 1000 * height), 0, height))
    if px1 <= px0 or py1 <= py0:
        return None
    return px0, py0, px1, py1


def _decode_mask(mask: str) -> np.ndarray | None:
    """Return the mask as a uint8 grayscale array, or None if the mask is missing."""
    text = (mask or "").strip()
    if text.startswith("data:"):
        _, _, text = text.partition(",")
    if not text:
        return None
    try:
        raw = base64.b64decode(text, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise _MaskError("mask is not valid base64") from exc
    if not raw:
        return None
    try:
        with PILImage.open(io.BytesIO(raw)) as im:
            im.load()
            return np.asarray(im.convert("L"), dtype=np.uint8)
    except Exception as exc:
        raise _MaskError("mask is not a decodable image") from exc


def _contour_polygon(component: np.ndarray) -> list[Point] | None:
    contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    epsilon = SIMPLIFY_EPSILON_FRACTION * cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
    if len(approx) < 3:
        return None
    return [(float(x), float(y)) for x, y in approx]


def segments_to_candidates(
    segments: list[GeminiSegment], width: int, height: int
) -> list[SegmentCandidate]:
    """Decode Gemini masks into simplified polygons in working-image pixels."""
    min_area = MIN_COMPONENT_FRACTION * width * height
    out: list[SegmentCandidate] = []
    for index, seg in enumerate(segments):
        label = seg.label.strip().lower()
        box = _box_to_px(seg.box_2d, width, height)
        if box is None:
            logger.warning("skipping segment %d (%s): invalid box %s", index, label, seg.box_2d)
            continue
        x0, y0, x1, y1 = box
        bw, bh = x1 - x0, y1 - y0
        try:
            mask = _decode_mask(seg.mask)
        except _MaskError as exc:
            logger.warning("skipping segment %d (%s): %s", index, label, exc)
            continue

        canvas = np.zeros((height, width), dtype=np.uint8)
        if mask is not None:
            resized = cv2.resize(mask, (max(1, bw), max(1, bh)), interpolation=cv2.INTER_LINEAR)
            canvas[y0:y1, x0:x1] = np.where(resized > MASK_THRESHOLD, 255, 0).astype(np.uint8)
            canvas = cv2.morphologyEx(canvas, cv2.MORPH_OPEN, OPEN_KERNEL)
        if mask is None or not canvas.any():
            # Missing or empty mask but a valid box: use the box rectangle itself.
            if bw * bh >= min_area:
                out.append(
                    SegmentCandidate(
                        label_hint=label,
                        polygon=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                        box=BoxPx(x0=x0, y0=y0, x1=x1, y1=y1),
                    )
                )
            continue

        count, labels, stats, _ = cv2.connectedComponentsWithStats(canvas, connectivity=8)
        for comp in range(1, count):
            area = stats[comp, cv2.CC_STAT_AREA]
            if area < min_area:
                continue
            polygon = _contour_polygon(np.where(labels == comp, 255, 0).astype(np.uint8))
            if polygon is None:
                continue
            cx, cy = stats[comp, cv2.CC_STAT_LEFT], stats[comp, cv2.CC_STAT_TOP]
            cw, ch = stats[comp, cv2.CC_STAT_WIDTH], stats[comp, cv2.CC_STAT_HEIGHT]
            out.append(
                SegmentCandidate(
                    label_hint=label,
                    polygon=polygon,
                    box=BoxPx(x0=float(cx), y0=float(cy), x1=float(cx + cw), y1=float(cy + ch)),
                )
            )
    return out


# ---------------------------------------------------------------- overlap resolution


def _priority(label: str) -> int:
    try:
        return LABEL_PRIORITY.index(label)  # type: ignore[arg-type]
    except ValueError:
        return len(LABEL_PRIORITY)


def _parts(geom) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if not g.is_empty]
    if hasattr(geom, "geoms"):  # GeometryCollection
        return [p for g in geom.geoms for p in _parts(g)]
    return []


def resolve_overlaps(
    candidates: list[SegmentCandidate], min_area_px: float = 0.0
) -> list[SegmentCandidate]:
    """Clip lower-priority candidates where they overlap higher-priority ones.

    Priority follows LABEL_PRIORITY (window/door first, wall last; unknown labels last).
    Polygons carry no holes, so a higher-priority shape lying fully inside another one
    (e.g. a window inside a wall) leaves the outer polygon unchanged; openings are
    subtracted later when areas are measured. Parts smaller than `min_area_px` are dropped.
    Output order follows the input order.
    """
    order = sorted(range(len(candidates)), key=lambda i: _priority(candidates[i].label_hint))
    taken = Polygon()
    resolved: dict[int, list[SegmentCandidate]] = {}
    for i in order:
        cand = candidates[i]
        shape = Polygon(cand.polygon).buffer(0)
        remaining = shape.difference(taken) if not taken.is_empty else shape
        parts: list[SegmentCandidate] = []
        for part in _parts(remaining):
            ext = Polygon(orient(part, sign=1.0).exterior)
            if ext.area <= 0 or ext.area < min_area_px:
                continue
            coords = [(float(x), float(y)) for x, y in list(ext.exterior.coords)[:-1]]
            if len(coords) < 3:
                continue
            minx, miny, maxx, maxy = ext.bounds
            parts.append(
                SegmentCandidate(
                    label_hint=cand.label_hint,
                    polygon=coords,
                    box=BoxPx(x0=minx, y0=miny, x1=maxx, y1=maxy),
                )
            )
        resolved[i] = parts
        taken = taken.union(shape) if not taken.is_empty else shape
    return [c for i in range(len(candidates)) for c in resolved[i]]
