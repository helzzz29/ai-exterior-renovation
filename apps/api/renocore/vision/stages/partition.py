"""C2 - surface detection with Gemini: JSON output, validation, ONE corrective re-ask.

Three output formats, selected by `SEGMENT_OUTPUT_MODE` (or the AI_SEGMENT_MODE env var):
- "labelmap" (default): the IMAGE model repaints the photo as a flat-colour label map, decoded by
  renocore.vision.legend (best edge alignment in live tests, one call)
- "mask":    {label, box_2d, mask}    -> masks decoded by renocore.pixels.segments_to_candidates
- "polygon": {label, box_2d, polygon} -> [[y, x], ...] points (0-1000) scaled to pixels here
"""

import base64
import binascii
import json
import os
import re
from typing import Any, Literal

import structlog
from google.genai import errors, types
from PIL.Image import Image
from pydantic import BaseModel

from renocore import pixels
from renocore.schemas.entities import LABELS, BoxPx, SegmentCandidate
from renocore.schemas.vision_io import GeminiSegment
from renocore.vision.gemini_adapter import GeminiClient
from renocore.vision.legend import decode_label_map
from renocore.vision.memo import FileCache, cache_key, sha256_bytes
from renocore.vision.payloads import closest_aspect_ratio, decode_image, encode_jpeg, encode_png
from renocore.vision.stages.compose import extract_image
from renocore.vision.templates import (
    SEGMENT_LABELMAP_PROMPT,
    SEGMENT_POLYGON_PROMPT,
    SEGMENT_PROMPT,
    load_prompt,
)

log = structlog.get_logger(__name__)

SegmentMode = Literal["labelmap", "mask", "polygon"]

# Default output format. Masks as base64 text were very slow and polygons rough on walls;
# the image-model label map aligned almost pixel-perfectly in one call.
SEGMENT_OUTPUT_MODE: SegmentMode = "labelmap"
SEGMENT_MODE_ENV = "AI_SEGMENT_MODE"

PROMPTS: dict[str, str] = {
    "labelmap": SEGMENT_LABELMAP_PROMPT,
    "mask": SEGMENT_PROMPT,
    "polygon": SEGMENT_POLYGON_PROMPT,
}
LABELMAP_IMAGE_SIZE = "1K"
LABELMAP_REASK = (
    "\n\nYour previous answer could not be used: {error} "
    "Return only the label map image, painted exactly as described."
)
MAX_OUTPUT_TOKENS: dict[str, int] = {"mask": 32768, "polygon": 8192}

# Live-checked on gemini-3.8-flash: thinking_level "low" works (MINIMAL is rejected with 400).
# For Gemini 2.x use ThinkingConfig(thinking_budget=0); None sends no thinking config.
# If the API rejects the config (400 mentioning "thinking"), the call is repeated once without
# a thinking config and that is remembered per model for the process.
SEGMENT_THINKING: types.ThinkingConfig | None = types.ThinkingConfig(
    thinking_level=types.ThinkingLevel.LOW
)
_thinking_rejected: set[str] = set()

MIN_AREA_FRACTION = 0.002  # polygons smaller than 0.2% of the image are dropped

LABEL_SYNONYMS: dict[str, str] = {
    "facade": "wall",
    "façade": "wall",
    "main_wall": "wall",
    "exterior_wall": "wall",
    "column": "pillar",
    "pillar_or_column": "pillar",
    "fascia": "roof_edge",
    "roof": "roof_edge",
    "roofline": "roof_edge",
    "eave": "roof_edge",
    "eaves": "roof_edge",
    "terrace": "balcony",
    "balustrade": "railing",
    "grille": "railing",
    "garage_door": "door",
    "entrance": "door",
}
REASK_SUFFIX = (
    "\n\nYour previous answer could not be used: {error}\n"
    "Return the complete corrected JSON list only, following every rule above."
)
TRUNCATED_ERROR = (
    "the answer was cut off because it was too long. Keep every item but use fewer points "
    "per outline (at most 12) and no extra text."
)


class SegmentationError(RuntimeError):
    """Gemini segmentation output stayed unusable after the corrective re-ask."""


class PolygonSegment(BaseModel):
    """Polygon-mode item: box_2d [y0, x0, y1, x1] and polygon [[y, x], ...], all 0-1000."""

    label: str
    box_2d: list[int]
    polygon: list[list[int]]


def output_mode() -> SegmentMode:
    value = os.environ.get(SEGMENT_MODE_ENV, SEGMENT_OUTPUT_MODE).strip().lower()
    if value not in PROMPTS:
        raise ValueError(
            f"{SEGMENT_MODE_ENV} must be 'labelmap', 'mask' or 'polygon', not {value!r}"
        )
    return value  # type: ignore[return-value]


def normalise_label(label: str) -> str | None:
    key = re.sub(r"[\s\-]+", "_", label.strip().lower())
    key = LABEL_SYNONYMS.get(key, key)
    return key if key in LABELS else None


def _strip_fences(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return match.group(1) if match else text


def _mask_ok(mask: str) -> bool:
    data = mask.split(",", 1)[1] if mask.startswith("data:") else mask
    try:
        raw = base64.b64decode(data, validate=False)
    except (binascii.Error, ValueError):
        return False
    return raw.startswith(b"\x89PNG")


def _check_box(i: int, label: str, box: Any) -> list[int]:
    numbers = isinstance(box, list) and all(isinstance(v, int | float) for v in box)
    if not numbers or len(box) != 4:
        raise ValueError(f"item {i} ({label}) box_2d must be four numbers [y0, x0, y1, x1].")
    y0, x0, y1, x1 = (int(round(v)) for v in box)
    if not all(0 <= v <= 1000 for v in (y0, x0, y1, x1)):
        raise ValueError(f"item {i} ({label}) box_2d {box} is out of the 0-1000 range.")
    if y0 >= y1 or x0 >= x1:
        raise ValueError(f"item {i} ({label}) box_2d {box} must have y0 < y1 and x0 < x1.")
    return [y0, x0, y1, x1]


def _check_polygon(i: int, label: str, polygon: Any) -> list[list[int]]:
    """[y, x] points clamped to 0-1000. Malformed structure is an error (re-ask)."""
    if not isinstance(polygon, list):
        raise ValueError(f"item {i} ({label}) polygon must be a list of [y, x] points.")
    points: list[list[int]] = []
    for p in polygon:
        if not isinstance(p, list) or len(p) != 2 or not all(isinstance(v, int | float) for v in p):
            raise ValueError(f"item {i} ({label}) polygon points must be [y, x] pairs.")
        y, x = (min(1000, max(0, int(round(v)))) for v in p)
        points.append([y, x])
    return points


def validate(text: str | None, mode: SegmentMode = "mask") -> list[Any]:
    """Parse and validate segmentation JSON. Raises ValueError with a message for the re-ask.

    Returns GeminiSegment items (mask mode) or PolygonSegment items (polygon mode). In mask mode
    an undecodable mask is blanked rather than re-asked (imaging then falls back to the box).
    """
    if not text or not text.strip():
        raise ValueError("the response was empty.")
    try:
        data = json.loads(_strip_fences(text))
    except json.JSONDecodeError as exc:
        raise ValueError(f"the response was not valid JSON ({exc.msg}).") from exc
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), None)
    if not isinstance(data, list):
        raise ValueError("the response must be a JSON list of items.")
    out: list[Any] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"item {i} is not a JSON object.")
        label = item.get("label")
        if not isinstance(label, str):
            raise ValueError(f"item {i} has no label.")
        if mode == "polygon":
            polygon = _check_polygon(i, label, item.get("polygon"))
            norm = normalise_label(label)
            if norm is None or len(polygon) < 3:
                log.info("segment_item_dropped", label=label, points=len(polygon))
                continue
            ys, xs = [p[0] for p in polygon], [p[1] for p in polygon]
            box = [min(ys), min(xs), max(ys), max(xs)]  # box from the polygon itself
            out.append(PolygonSegment(label=norm, box_2d=box, polygon=polygon))
            continue
        box = _check_box(i, label, item.get("box_2d"))
        mask = item.get("mask")
        if not isinstance(mask, str) or not _mask_ok(mask):
            log.info("segment_mask_unusable", label=label)
            mask = ""
        norm = normalise_label(label)
        if norm is None:
            log.info("segment_label_dropped", label=label)
            continue
        out.append(GeminiSegment(label=norm, box_2d=box, mask=mask))
    if not any(s.label == "wall" for s in out):
        raise ValueError("no wall was returned; every visible wall must be included.")
    return out


def thinking_for(model: str) -> types.ThinkingConfig | None:
    return None if model in _thinking_rejected else SEGMENT_THINKING


def build_config(model: str = "", mode: SegmentMode = "mask") -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
        max_output_tokens=MAX_OUTPUT_TOKENS[mode],
        thinking_config=thinking_for(model),
    )


def build_contents(
    photo_jpeg: bytes, error: str | None = None, mode: SegmentMode = "mask"
) -> list[Any]:
    prompt = load_prompt(PROMPTS[mode])
    if error:
        prompt += REASK_SUFFIX.format(error=error)
    return [types.Part.from_bytes(data=photo_jpeg, mime_type="image/jpeg"), prompt]


def _is_thinking_rejection(exc: BaseException) -> bool:
    if not isinstance(exc, errors.ClientError) or exc.code != 400:
        return False
    return "thinking" in str(exc).lower()


async def _call(
    gemini: GeminiClient, model: str, mode: SegmentMode, contents: list[Any], input_hash: str
) -> Any:
    kwargs = dict(
        step="C2",
        model=model,
        contents=contents,
        prompt_version=PROMPTS[mode],
        input_hash=input_hash,
    )
    try:
        return await gemini.generate(config=build_config(model, mode), **kwargs)
    except errors.ClientError as exc:
        if thinking_for(model) is None or not _is_thinking_rejection(exc):
            raise
        log.warning("segment_thinking_config_rejected", model=model, error=str(exc)[:200])
        _thinking_rejected.add(model)
        return await gemini.generate(config=build_config(model, mode), **kwargs)


def _finish_reason(response: Any) -> str | None:
    for cand in getattr(response, "candidates", None) or []:
        reason = getattr(cand, "finish_reason", None)
        if reason is not None:
            return str(getattr(reason, "value", reason))
    return None


def response_text(response: Any) -> str:
    """Text of the response; raises ValueError (re-askable) when cut off or empty."""
    if _finish_reason(response) == "MAX_TOKENS":
        raise ValueError(TRUNCATED_ERROR)
    try:
        text = response.text
    except Exception:  # blocked/odd responses
        text = None
    if not text or not text.strip():
        raise ValueError("the response was empty.")
    return text


def _summary(segments: list[Any]) -> dict:
    return {"segments": [{"label": s.label, "box_2d": s.box_2d} for s in segments]}


async def segments_for(
    gemini: GeminiClient,
    cache: FileCache | None,
    model: str,
    photo: Image,
    mode: SegmentMode | None = None,
) -> list[Any]:
    mode = mode or output_mode()
    prompt_version = PROMPTS[mode]
    item_type = GeminiSegment if mode == "mask" else PolygonSegment
    photo_jpeg = encode_jpeg(photo)
    key = cache_key("C2", model, prompt_version, [sha256_bytes(photo_jpeg)], {"mode": mode})
    if cache is not None:
        hit = cache.get_json(key)
        if hit is not None:
            segments = [item_type.model_validate(s) for s in hit]
            await gemini.record_cached(
                step="C2",
                model=model,
                prompt_version=prompt_version,
                input_hash=key,
                output=_summary(segments),
            )
            return segments

    error: str | None = None
    for attempt in range(2):
        call = await _call(gemini, model, mode, build_contents(photo_jpeg, error, mode), key)
        try:
            segments = validate(response_text(call.response), mode)
        except ValueError as exc:
            error = str(exc)
            await gemini.record(
                call,
                step="C2",
                model=model,
                prompt_version=prompt_version,
                input_hash=key,
                output=None,
                error=f"invalid output (attempt {attempt + 1}): {error}",
            )
            continue
        await gemini.record(
            call,
            step="C2",
            model=model,
            prompt_version=prompt_version,
            input_hash=key,
            output=_summary(segments),
        )
        if cache is not None:
            cache.put_json(key, [s.model_dump() for s in segments])
        return segments
    raise SegmentationError(f"Surface detection returned unusable output twice: {error}")


def polygons_to_candidates(
    segments: list[PolygonSegment], width: int, height: int
) -> list[SegmentCandidate]:
    """Scale [y, x] 0-1000 points to working-image pixels (clamped to the image); box from
    the polygon; drop shapes with < 3 points or smaller than 0.2% of the image."""
    min_area = MIN_AREA_FRACTION * width * height
    out: list[SegmentCandidate] = []
    for s in segments:
        polygon = [
            (min(width, max(0.0, x * width / 1000)), min(height, max(0.0, y * height / 1000)))
            for y, x in s.polygon
        ]
        if len(polygon) < 3 or pixels.polygon_area_px(polygon) < max(min_area, 1.0):
            log.info("segment_polygon_dropped", label=s.label)
            continue
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        box = BoxPx(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))
        out.append(SegmentCandidate(label_hint=s.label, polygon=polygon, box=box))
    return out


# ---------------------------------------------------------------- label-map mode


def build_labelmap_config(width: int, height: int) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(
            aspect_ratio=closest_aspect_ratio(width, height), image_size=LABELMAP_IMAGE_SIZE
        ),
    )


def build_labelmap_contents(photo_jpeg: bytes, error: str | None = None) -> list[Any]:
    prompt = load_prompt(SEGMENT_LABELMAP_PROMPT)
    if error:
        prompt += LABELMAP_REASK.format(error=error)
    return [types.Part.from_bytes(data=photo_jpeg, mime_type="image/jpeg"), prompt]


def labelmap_candidates_from(
    response: Any, width: int, height: int
) -> tuple[bytes, list[SegmentCandidate]]:
    """Decode the response image. Raises ValueError (re-askable) if unusable."""

    data, text = extract_image(response)
    if not data:
        raise ValueError(f"no image was returned ({text or 'no explanation'}).")
    try:
        image = decode_image(data)
    except OSError as exc:
        raise ValueError("the returned image could not be read.") from exc
    candidates = decode_label_map(image, width, height)
    if not any(c.label_hint == "wall" for c in candidates):
        raise ValueError("no red wall area was painted; every exterior wall must be pure red.")
    return encode_png(image), candidates


def _labelmap_summary(candidates: list[SegmentCandidate]) -> dict:
    counts: dict[str, int] = {}
    for c in candidates:
        counts[c.label_hint] = counts.get(c.label_hint, 0) + 1
    return {"counts": counts}


async def labelmap_run(
    gemini: GeminiClient, cache: FileCache | None, model: str, photo: Image
) -> list[SegmentCandidate]:
    prompt_version = SEGMENT_LABELMAP_PROMPT
    photo_jpeg = encode_jpeg(photo)
    key = cache_key("C2", model, prompt_version, [sha256_bytes(photo_jpeg)], {"mode": "labelmap"})
    w, h = photo.width, photo.height
    if cache is not None:
        hit = cache.get_bytes(key, ".png")
        if hit is not None:
            candidates = decode_label_map(decode_image(hit), w, h)
            await gemini.record_cached(
                step="C2",
                model=model,
                prompt_version=prompt_version,
                input_hash=key,
                output=_labelmap_summary(candidates),
            )
            return candidates

    error: str | None = None
    config = build_labelmap_config(w, h)
    for attempt in range(2):
        call = await gemini.generate(
            step="C2",
            model=model,
            contents=build_labelmap_contents(photo_jpeg, error),
            config=config,
            prompt_version=prompt_version,
            input_hash=key,
        )
        try:
            png, candidates = labelmap_candidates_from(call.response, w, h)
        except ValueError as exc:
            error = str(exc)
            await gemini.record(
                call,
                step="C2",
                model=model,
                prompt_version=prompt_version,
                input_hash=key,
                output=None,
                error=f"invalid output (attempt {attempt + 1}): {error}",
            )
            continue
        await gemini.record(
            call,
            step="C2",
            model=model,
            prompt_version=prompt_version,
            input_hash=key,
            output=_labelmap_summary(candidates),
        )
        if cache is not None:
            cache.put_bytes(key, png, ".png")
        return candidates
    raise SegmentationError(f"Surface detection returned unusable output twice: {error}")


async def run(
    gemini: GeminiClient,
    cache: FileCache | None,
    model: str,
    photo: Image,
    mode: SegmentMode | None = None,
    image_model: str | None = None,
) -> list[SegmentCandidate]:
    """C2. `model` is the text segmentation model; label-map mode uses `image_model`."""
    mode = mode or output_mode()
    if mode == "labelmap":
        return await labelmap_run(gemini, cache, image_model or model, photo)
    segments = await segments_for(gemini, cache, model, photo, mode)
    if mode == "polygon":
        return polygons_to_candidates(segments, photo.width, photo.height)
    return pixels.segments_to_candidates(segments, photo.width, photo.height)
