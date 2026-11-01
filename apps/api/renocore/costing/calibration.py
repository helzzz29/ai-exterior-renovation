"""Scale resolver: pixels -> feet (estimation.md section 1)."""

from __future__ import annotations

import math
import statistics

from renocore.schemas.entities import (
    BoxPx,
    Confidence,
    Region,
    ScaleInputs,
    ScaleMethod,
    ScaleResult,
)

from .surfaces import box_height, box_width, union_bbox

DOOR_HEIGHT_FT = 7.0
WINDOW_HEIGHT_FT = 4.0
STOREY_HEIGHT_FT = 10.0
DOOR_VISIBLE_MIN = 0.7
DOOR_AGREEMENT = 0.10  # Gemini door region vs Jev box height
WINDOW_SPREAD_MAX = 0.15  # max/min - 1 across approved windows

_CONF_ORDER = {Confidence.low: 0, Confidence.medium: 1, Confidence.high: 2}


def silhouette(regions: list[Region]) -> BoxPx | None:
    """Box around all wall and parapet regions; falls back to all regions."""
    building = [r for r in regions if r.label in ("wall", "parapet")]
    return union_bbox(building) or union_bbox(regions)


def geometric_mean(values: list[float]) -> float:
    return math.exp(sum(math.log(v) for v in values) / len(values))


def _region_box(region: Region) -> BoxPx:
    box = union_bbox([region])
    assert box is not None  # a region always has >= 3 points
    return box


# ---------------------------------------------------------------- candidates


def scale_from_measurement(inputs: ScaleInputs, sil: BoxPx | None) -> float | None:
    """Priority 1: user measurement(s). Geometric mean when several are given."""
    m = inputs.measurements
    factors: list[float] = []
    if m.facade_width_ft and box_width(sil) > 0:
        factors.append(m.facade_width_ft / box_width(sil))
    if m.facade_height_ft and box_height(sil) > 0:
        factors.append(m.facade_height_ft / box_height(sil))
    line = m.reference_line
    if line is not None:
        px = math.hypot(line.x2 - line.x1, line.y2 - line.y1)
        if px > 0:
            factors.append(line.length_ft / px)
    return geometric_mean(factors) if factors else None


def scale_from_door(inputs: ScaleInputs) -> tuple[float, Confidence, BoxPx] | None:
    """Priority 2: main door (7 ft). Medium if an approved door region agrees within 10%."""
    box = inputs.door_box_px
    if box is None or (inputs.door_visible or 0.0) < DOOR_VISIBLE_MIN:
        return None
    h = box_height(box)
    if h <= 0:
        return None
    doors = [_region_box(r) for r in inputs.regions if r.label == "door"]
    agrees = any(abs(box_height(d) - h) <= DOOR_AGREEMENT * h for d in doors)
    return DOOR_HEIGHT_FT / h, (Confidence.medium if agrees else Confidence.low), box


def scale_from_windows(inputs: ScaleInputs) -> tuple[float, BoxPx] | None:
    """Priority 3: >= 2 windows of similar height (4 ft each)."""
    boxes = [_region_box(r) for r in inputs.regions if r.label == "window"]
    boxes = [b for b in boxes if box_height(b) > 0]
    if len(boxes) < 2:
        return None
    heights = [box_height(b) for b in boxes]
    if max(heights) >= min(heights) * (1 + WINDOW_SPREAD_MAX):
        return None
    median = statistics.median(heights)
    ref = min(boxes, key=lambda b: abs(box_height(b) - median))
    return WINDOW_HEIGHT_FT / median, ref


def floor_count(inputs: ScaleInputs) -> int:
    return inputs.measurements.floors or inputs.floors_answer or 1


def scale_from_floors(inputs: ScaleInputs, sil: BoxPx | None) -> float | None:
    """Priority 4: floors x 10 ft over the building height."""
    h = box_height(sil)
    if h <= 0:
        return None
    return floor_count(inputs) * STOREY_HEIGHT_FT / h


# ---------------------------------------------------------------- explanation


def _fmt_ft(x: float) -> str:
    return f"{x:.0f}" if x >= 10 else f"{x:.1f}".rstrip("0").rstrip(".")


def explain(
    method: ScaleMethod, confidence: Confidence, width_ft: float | None, floors: int
) -> str:
    """Plain-language sentence for the size check screen."""
    if method == ScaleMethod.user_measurement:
        lead = "We used the measurement you gave us."
    elif method == ScaleMethod.door:
        lead = f"We used your main door as a guide (standard height {DOOR_HEIGHT_FT:.0f} ft)."
    elif method == ScaleMethod.windows:
        lead = f"We used your windows as a guide (standard height {WINDOW_HEIGHT_FT:.0f} ft)."
    else:
        word = "floor" if floors == 1 else "floors"
        lead = (
            f"We used the number of floors as a guide ({floors} {word}, "
            f"about {STOREY_HEIGHT_FT:.0f} ft each)."
        )
    parts = [lead]
    if width_ft is not None:
        parts.append(f"That makes your house about {_fmt_ft(width_ft)} ft wide.")
    if confidence == Confidence.low:
        parts.append(
            "This is only a rough guess. Please measure the width of your house, or draw a "
            "line on the photo and tell us its real length, so the estimate can be finalised."
        )
    return " ".join(parts)


# ---------------------------------------------------------------- resolver


def resolve_scale(inputs: ScaleInputs) -> ScaleResult:
    """Pick the most reliable scale source (priority chain, estimation.md section 1)."""
    sil = silhouette(inputs.regions)
    ref: BoxPx | None = None
    measured = scale_from_measurement(inputs, sil)
    if measured is not None:
        ft, method, conf = measured, ScaleMethod.user_measurement, Confidence.high
    else:
        door = scale_from_door(inputs)
        windows = scale_from_windows(inputs)
        if door is not None and (door[1] == Confidence.medium or windows is None):
            ft, conf, ref = door
            method = ScaleMethod.door
        elif windows is not None:
            ft, ref = windows
            method, conf = ScaleMethod.windows, Confidence.medium
        else:
            floors_ft = scale_from_floors(inputs, sil)
            if floors_ft is None:
                raise ValueError("Cannot work out the size of the house: no surfaces found")
            ft, method, conf = floors_ft, ScaleMethod.floors, Confidence.low

    if inputs.photo_warned and _CONF_ORDER[conf] > _CONF_ORDER[Confidence.medium]:
        conf = Confidence.medium
    width_ft = box_width(sil) * ft if sil is not None and box_width(sil) > 0 else None
    return ScaleResult(
        ft_per_px=ft,
        method=method,
        confidence=conf,
        facade_width_ft=width_ft,
        reference_box_px=ref,
        explanation=explain(method, conf, width_ft, floor_count(inputs)),
        needs_measurement=conf == Confidence.low,
    )
