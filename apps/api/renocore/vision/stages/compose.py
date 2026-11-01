"""C5 - redesign request (Gemini image model) and the render loop.

zones -> zone map -> C5 -> composite -> C6, auto-regenerating with fix notes.
"""

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from google.genai import types
from PIL.Image import Image

from renocore import pixels
from renocore.schemas.entities import (
    OPENING_LABELS,
    Assignment,
    Material,
    QAResult,
    Region,
    Zone,
)
from renocore.schemas.vision_io import AIProvider
from renocore.vision.gemini_adapter import GeminiClient
from renocore.vision.guardrails import qa_from_scores, qa_min_score
from renocore.vision.memo import FileCache, cache_key, sha256_bytes
from renocore.vision.payloads import (
    VARIANT_SEP,
    closest_aspect_ratio,
    decode_image,
    encode_jpeg,
    encode_png,
    load_swatch,
)
from renocore.vision.templates import RENDER_PROMPT, render_prompt

log = structlog.get_logger(__name__)

IMAGE_SIZE = "2K"
RESPONSE_MODALITIES = ["TEXT", "IMAGE"]

# Distinct, nameable zone colours (named in the prompt and in QA fix notes).
ZONE_PALETTE: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("red", (230, 25, 45)),
    ("blue", (0, 90, 230)),
    ("yellow", (255, 225, 0)),
    ("green", (40, 180, 60)),
    ("magenta", (240, 40, 220)),
    ("cyan", (0, 220, 230)),
    ("orange", (255, 130, 0)),
    ("purple", (120, 30, 180)),
    ("lime", (170, 255, 60)),
    ("pink", (255, 150, 190)),
    ("brown", (140, 80, 30)),
    ("white", (255, 255, 255)),
)


class RenderError(RuntimeError):
    """The image model returned no usable image."""


# ---------------------------------------------------------------- zones


def build_zones(
    regions: list[Region], assignments: list[Assignment], materials: dict[str, Material]
) -> tuple[list[Zone], dict[str, Material]]:
    """One zone per (material, colour), in first-assigned order, each with a distinct colour.

    A chosen colour that differs from the catalogue default becomes a colour variant material
    (id "<id>@<hex>") so the prompt, swatch and QA all see the exact colour.
    Returns the zones and the material dict to render with (catalogue + variants).
    """
    by_id = {r.id: r for r in regions}
    groups: dict[str, list[str]] = {}
    render_materials = dict(materials)
    for a in assignments:
        region = by_id.get(a.region_id)
        material = materials.get(a.material_id)
        if region is None or material is None or region.label in OPENING_LABELS:
            continue
        mid = material.id
        color = a.color.lower() if a.color else None
        default = material.default_color.lower() if material.default_color else None
        if color and material.colorable and color != default:
            mid = f"{material.id}{VARIANT_SEP}{color.lstrip('#')}"
            render_materials[mid] = material.model_copy(update={"id": mid, "default_color": color})
        groups.setdefault(mid, []).append(region.id)
    if len(groups) > len(ZONE_PALETTE):
        raise ValueError(f"At most {len(ZONE_PALETTE)} different finishes can be shown at once.")
    zones = [
        Zone(region_ids=ids, material_id=mid, color_name=name, rgb=rgb)
        for (mid, ids), (name, rgb) in zip(groups.items(), ZONE_PALETTE, strict=False)
    ]
    return zones, render_materials


# ---------------------------------------------------------------- C5 request


def zone_legend(zones: list[Zone], materials: dict[str, Material]) -> str:
    lines = []
    for i, zone in enumerate(zones):
        m = materials[zone.material_id]
        colour = f" in colour {m.default_color}" if m.colorable and m.default_color else ""
        lines.append(
            f"- {zone.color_name} zone -> {m.name}{colour} (sample: image {i + 3}). {m.description}"
        )
    return "\n".join(lines)


def build_prompt(
    zones: list[Zone],
    materials: dict[str, Material],
    user_note: str | None,
    fix_notes: list[str] | None,
) -> str:
    note = (
        f"\nThe homeowner also asked: {user_note.strip()}\n"
        if user_note and user_note.strip()
        else ""
    )
    fixes = ""
    if fix_notes:
        fixes = "\nFix these problems from the previous attempt:\n" + "\n".join(
            f"- Fix: {n}" for n in fix_notes
        )
        fixes += "\n"
    return render_prompt(
        RENDER_PROMPT,
        zone_legend=zone_legend(zones, materials),
        user_note_section=note,
        fix_section=fixes,
    )


def build_config(width: int, height: int) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        response_modalities=RESPONSE_MODALITIES,
        image_config=types.ImageConfig(
            aspect_ratio=closest_aspect_ratio(width, height), image_size=IMAGE_SIZE
        ),
    )


def build_contents(
    photo_jpeg: bytes, zone_map_png: bytes, swatch_pngs: list[bytes], prompt: str
) -> list[Any]:
    parts: list[Any] = [
        types.Part.from_bytes(data=photo_jpeg, mime_type="image/jpeg"),
        types.Part.from_bytes(data=zone_map_png, mime_type="image/png"),
    ]
    parts += [types.Part.from_bytes(data=s, mime_type="image/png") for s in swatch_pngs]
    parts.append(prompt)
    return parts


def extract_image(response: Any) -> tuple[bytes | None, str | None]:
    """First non-thought inline image in the response, plus any text the model returned."""
    texts: list[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            blob = getattr(part, "inline_data", None)
            if blob is not None and blob.data and (blob.mime_type or "").startswith("image/"):
                return blob.data, "\n".join(texts) or None
            if getattr(part, "text", None):
                texts.append(part.text)
    return None, "\n".join(texts) or None


async def generate(
    gemini: GeminiClient,
    cache: FileCache | None,
    model: str,
    seed_dir: Path,
    photo: Image,
    zone_map: Image,
    zones: list[Zone],
    materials: dict[str, Material],
    user_note: str | None,
    fix_notes: list[str] | None,
    attempt: int = 0,
    cache_salt: str | None = None,
) -> Image:
    """C5. The cache key covers all inputs plus attempt index and `cache_salt` (a render id),
    so an explicit redo never returns a cached image."""
    photo_jpeg = encode_jpeg(photo)
    zone_png = encode_png(zone_map.convert("RGB"))
    swatches = [encode_png(load_swatch(seed_dir, materials[z.material_id])) for z in zones]
    prompt = build_prompt(zones, materials, user_note, fix_notes)
    hashes = [sha256_bytes(b) for b in (photo_jpeg, zone_png, *swatches)]
    key = cache_key(
        "C5",
        model,
        RENDER_PROMPT,
        hashes,
        {
            "prompt": prompt,
            "attempt": attempt,
            "notes": fix_notes or [],
            "user_note": user_note,
            "salt": cache_salt,
        },
    )
    if cache is not None:
        hit = cache.get_bytes(key, ".png")
        if hit is not None:
            await gemini.record_cached(
                step="C5",
                model=model,
                prompt_version=RENDER_PROMPT,
                input_hash=key,
                output={"bytes": len(hit), "attempt": attempt},
            )
            return decode_image(hit)

    contents = build_contents(photo_jpeg, zone_png, swatches, prompt)
    config = build_config(photo.width, photo.height)
    data: bytes | None = None
    text: str | None = None
    for ask in range(2):  # one re-ask if the model answered without an image
        call = await gemini.generate(
            step="C5",
            model=model,
            contents=contents,
            config=config,
            prompt_version=RENDER_PROMPT,
            input_hash=key,
        )
        data, text = extract_image(call.response)
        await gemini.record(
            call,
            step="C5",
            model=model,
            prompt_version=RENDER_PROMPT,
            input_hash=key,
            output={"bytes": len(data) if data else 0, "attempt": attempt, "text": text},
            error=None if data else f"no image in response (try {ask + 1})",
        )
        if data:
            break
        contents = [*contents[:-1], prompt + "\n\nReturn the edited photo as an image."]
    if not data:
        raise RenderError(f"The image model returned no image: {text or 'no explanation'}")
    image = decode_image(data)
    if cache is not None:
        cache.put_bytes(key, encode_png(image), ".png")
    return image


# ---------------------------------------------------------------- render loop


@dataclass
class RenderOutcome:
    image: Image  # composited final image
    zone_map: Image
    qa: QAResult
    attempts: int


def _accepted_params(provider: AIProvider) -> set[str]:
    try:
        return set(inspect.signature(provider.generate_redesign).parameters)
    except (TypeError, ValueError):
        return set()


async def render_design(
    provider: AIProvider,
    photo: Image,
    regions: list[Region],
    assignments: list[Assignment],
    materials: dict[str, Material],
    user_note: str | None,
    max_auto_regenerate: int,
    qa_threshold: float,
    cache_salt: str | None = None,
) -> RenderOutcome:
    """Zones -> zone map -> C5 -> composite -> C6, auto-regenerating with fix notes.

    Returns the first passing attempt, otherwise the attempt with the highest minimum QA score.
    `cache_salt` (e.g. the render id) is passed to the provider's cache key so that an explicit
    redo by the user always generates a fresh image; the attempt index is passed as well.
    """
    zones, render_materials = build_zones(regions, assignments, materials)
    if not zones:
        raise ValueError("Choose a material for at least one part of the house first.")
    by_id = {r.id: r for r in regions}
    zmap = pixels.zone_map(
        photo, [([by_id[rid].polygon for rid in z.region_ids], z.rgb) for z in zones]
    )
    include = [by_id[rid].polygon for z in zones for rid in z.region_ids]
    exclude = [r.polygon for r in regions if r.label in OPENING_LABELS]
    accepted = _accepted_params(provider)

    best: tuple[float, Image, QAResult] | None = None
    fix_notes: list[str] | None = None
    total = 1 + max(0, max_auto_regenerate)
    for attempt in range(total):
        kwargs: dict[str, Any] = {}
        if "attempt" in accepted:
            kwargs["attempt"] = attempt
        if "cache_salt" in accepted:
            kwargs["cache_salt"] = cache_salt
        raw = await provider.generate_redesign(
            photo, zmap, zones, render_materials, user_note, fix_notes, **kwargs
        )
        final = pixels.composite(photo, raw, include=include, exclude=exclude)
        del raw  # the model's full-size image is not needed after compositing
        checked = await provider.check_render(photo, final, zmap, zones, render_materials)
        qa = qa_from_scores(
            checked.openings_preserved,
            checked.structure_preserved,
            checked.zones,
            zones,
            render_materials,
            qa_threshold,
        )
        log.info("render_attempt", attempt=attempt + 1, passed=qa.passed, failed=qa.failed_checks)
        if qa.passed:
            return RenderOutcome(image=final, zone_map=zmap, qa=qa, attempts=attempt + 1)
        score = qa_min_score(qa)
        if best is None or score > best[0]:
            best = (score, final, qa)
        fix_notes = qa.failed_checks
    assert best is not None
    return RenderOutcome(image=best[1], zone_map=zmap, qa=best[2], attempts=total)
