"""Region crops (C3/C4), zone maps (C5 input) and mask-bounded compositing (C5 output)."""

import math

import cv2
import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw
from PIL.Image import Image

from app.domain.models import Point
from app.imaging.geometry import fill_polygons, polygon_box, polygons_mask

OUTLINE_RGB = (255, 0, 0)
OUTLINE_WIDTH_FRACTION = 0.006
ZONE_DIM_FACTOR = 0.45
ZONE_DESATURATE = 0.3  # share of grey mixed into the dimmed photo
ASPECT_TOLERANCE = 0.01


def _rgb(img: Image) -> Image:
    return img if img.mode == "RGB" else img.convert("RGB")


def region_crop(img: Image, polygon: list[Point], pad: float = 0.25, outline: bool = True) -> Image:
    """Bounding-box crop padded by `pad`, polygon outlined in red."""
    img = _rgb(img)
    width, height = img.size
    box = polygon_box(polygon)
    bw, bh = box.x1 - box.x0, box.y1 - box.y0
    x0 = max(0, math.floor(box.x0 - pad * bw))
    y0 = max(0, math.floor(box.y0 - pad * bh))
    x1 = min(width, math.ceil(box.x1 + pad * bw))
    y1 = min(height, math.ceil(box.y1 + pad * bh))
    x0, y0 = min(x0, width - 1), min(y0, height - 1)
    x1, y1 = max(x1, x0 + 1), max(y1, y0 + 1)
    crop = img.crop((x0, y0, x1, y1))
    if outline and len(polygon) >= 2:
        cw, ch = crop.size
        line_w = max(2, round(OUTLINE_WIDTH_FRACTION * max(cw, ch)))
        pts = [(px - x0, py - y0) for px, py in polygon]
        draw = ImageDraw.Draw(crop)
        draw.line([*pts, pts[0]], fill=OUTLINE_RGB, width=line_w, joint="curve")
    return crop


def zone_map(img: Image, zones: list[tuple[list[list[Point]], tuple[int, int, int]]]) -> Image:
    """Dimmed photo with each zone's polygons filled in a flat colour.

    Works one colour channel at a time so only single-channel float arrays exist at once.
    """
    src = np.asarray(_rgb(img), dtype=np.uint8)
    grey = src.mean(axis=2, dtype=np.float32)
    out = np.empty_like(src)
    for c in range(3):
        dimmed = (1 - ZONE_DESATURATE) * src[..., c].astype(np.float32) + ZONE_DESATURATE * grey
        dimmed *= ZONE_DIM_FACTOR
        out[..., c] = np.clip(np.round(dimmed), 0, 255)
    for polygons, rgb in zones:
        fill_polygons(out, polygons, tuple(int(c) for c in rgb))
    return PILImage.fromarray(out)


def _match_aspect(generated: Image, width: int, height: int) -> Image:
    gw, gh = generated.size
    target = width / height
    current = gw / gh
    if abs(current / target - 1) > ASPECT_TOLERANCE:
        if current > target:  # too wide: crop the sides
            new_w = max(1, round(gh * target))
            left = (gw - new_w) // 2
            generated = generated.crop((left, 0, left + new_w, gh))
        else:  # too tall: crop top and bottom
            new_h = max(1, round(gw / target))
            top = (gh - new_h) // 2
            generated = generated.crop((0, top, gw, top + new_h))
    if generated.size != (width, height):
        generated = generated.resize((width, height), PILImage.Resampling.LANCZOS)
    return generated


def composite_alpha(
    size: tuple[int, int],
    include: list[list[Point]],
    exclude: list[list[Point]],
    feather_px: int = 3,
) -> np.ndarray:
    """Float alpha in [0, 1]; exactly 0 outside include-minus-exclude, feathered inward."""
    mask = polygons_mask(size, include)
    fill_polygons(mask, exclude, 0)
    if feather_px <= 0:
        return (mask > 0).astype(np.float32)
    k = 2 * feather_px + 1
    eroded = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    blurred = cv2.GaussianBlur(eroded.astype(np.float32) / 255.0, (k, k), 0)
    alpha = np.clip(blurred, 0.0, 1.0)
    alpha[mask == 0] = 0.0
    return alpha


def composite(
    original: Image,
    generated: Image,
    include: list[list[Point]],
    exclude: list[list[Point]],
    feather_px: int = 3,
) -> Image:
    """Resize generated to original; keep generated pixels only inside include minus exclude.

    Blends through an 8-bit mask (no float copies of the full images, which matters on a
    512 MB server): pixels with alpha 0 are the original and alpha 1 the generated image
    exactly; the feathered edge is within one colour level of an exact float blend.
    """
    original = _rgb(original)
    width, height = original.size
    gen = _match_aspect(_rgb(generated), width, height)
    alpha = composite_alpha((width, height), include, exclude, feather_px)
    np.multiply(alpha, 255.0, out=alpha)
    np.rint(alpha, out=alpha)
    mask = PILImage.fromarray(alpha.astype(np.uint8), "L")
    del alpha
    return PILImage.composite(gen, original, mask)
