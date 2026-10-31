"""Decode a flat-colour semantic label map (C2 "labelmap" mode) into SegmentCandidates.

The image model repaints the photo with one flat colour per surface type. Its output may be a
slightly different size/aspect and JPEG-compressed, so pixels are classified to the nearest palette
colour (within a distance threshold) at native size, the class map is resized to the working photo
with NEAREST, cleaned per class, and every connected component becomes a simplified polygon.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from PIL.Image import Image

from app.domain.models import BoxPx, SegmentCandidate

# class name -> RGB, in the order used by the prompt (segment_v3). "roof" and "background" are
# not part of the label taxonomy: roof becomes roof_edge only for thin bands; background is dropped.
PALETTE: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("wall", (255, 0, 0)),
    ("window", (0, 0, 255)),
    ("door", (0, 255, 0)),
    ("pillar", (255, 0, 255)),
    ("balcony", (255, 128, 0)),
    ("parapet", (0, 255, 255)),
    ("railing", (255, 255, 0)),
    ("gate", (128, 64, 0)),
    ("roof", (255, 255, 255)),
    ("background", (0, 0, 0)),
)
BACKGROUND = len(PALETTE) - 1
MAX_COLOUR_DISTANCE = 90.0  # RGB euclidean; farther pixels count as background
KERNEL_FRACTION = 0.003  # morphology kernel ~0.3% of the shorter side
MIN_AREA_FRACTION = 0.002  # components below 0.2% of the image are dropped ...
MIN_OPENING_AREA_FRACTION = 0.0005  # ... except windows/doors (0.05%) so small ones survive
ROOF_EDGE_MAX_HEIGHT = 0.15  # white bands thinner than 15% of image height are roof edges
APPROX_EPSILON = 0.003  # approxPolyDP epsilon as a fraction of the contour perimeter
OPENINGS = frozenset({"window", "door"})


@dataclass
class LabelMapStats:
    class_pixels: dict[str, int]


def classify(label_map: Image) -> np.ndarray:
    """Per-pixel palette index (uint8) at the label map's native size."""
    rgb = np.asarray(label_map.convert("RGB"), dtype=np.int32)
    colours = np.array([c for _, c in PALETTE], dtype=np.int32)
    h, w, _ = rgb.shape
    flat = rgb.reshape(-1, 1, 3)
    best = np.zeros(flat.shape[0], dtype=np.uint8)
    best_d = np.full(flat.shape[0], np.iinfo(np.int32).max, dtype=np.int64)
    for i, colour in enumerate(colours):  # loop keeps memory at one distance array
        d = ((flat[:, 0, :] - colour) ** 2).sum(axis=1)
        closer = d < best_d
        best[closer] = i
        best_d[closer] = d[closer]
    best[best_d > MAX_COLOUR_DISTANCE**2] = BACKGROUND
    return best.reshape(h, w)


def _kernel(width: int, height: int) -> np.ndarray:
    k = max(3, int(round(KERNEL_FRACTION * min(width, height))))
    k += 1 - k % 2  # odd
    return cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))


def decode_label_map(label_map: Image, width: int, height: int) -> list[SegmentCandidate]:
    """Label map -> candidates in working-image pixels (width x height)."""
    classes = classify(label_map)
    if classes.shape != (height, width):
        classes = cv2.resize(classes, (width, height), interpolation=cv2.INTER_NEAREST)
    kernel = _kernel(width, height)
    image_area = width * height
    out: list[SegmentCandidate] = []
    for index, (name, _) in enumerate(PALETTE[:BACKGROUND]):
        mask = np.where(classes == index, 255, 0).astype(np.uint8)
        if not mask.any():
            continue
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        fraction = MIN_OPENING_AREA_FRACTION if name in OPENINGS else MIN_AREA_FRACTION
        min_area = fraction * image_area
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        found: list[SegmentCandidate] = []
        for comp in range(1, count):
            x, y, w, h, area = (int(v) for v in stats[comp])
            if area < min_area:
                continue
            label = name
            if name == "roof":
                if h >= ROOF_EDGE_MAX_HEIGHT * height:
                    continue  # roof surfaces are not priced
                label = "roof_edge"
            component = np.where(labels == comp, 255, 0).astype(np.uint8)
            contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:  # pragma: no cover - a non-empty component always has a contour
                continue
            contour = max(contours, key=cv2.contourArea)
            approx = cv2.approxPolyDP(contour, APPROX_EPSILON * cv2.arcLength(contour, True), True)
            points = [(float(px), float(py)) for px, py in approx.reshape(-1, 2)]
            if len(points) < 3:
                points = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            found.append(
                SegmentCandidate(
                    label_hint=label,
                    polygon=points,
                    box=BoxPx(x0=float(x), y0=float(y), x1=float(x + w), y1=float(y + h)),
                )
            )
        found.sort(key=lambda c: (c.box.y0, c.box.x0))
        out.extend(found)
    return out


def class_pixels(label_map: Image) -> dict[str, int]:
    classes = classify(label_map)
    counts = np.bincount(classes.ravel(), minlength=len(PALETTE))
    return {name: int(counts[i]) for i, (name, _) in enumerate(PALETTE)}
