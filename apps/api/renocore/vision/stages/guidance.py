"""C4 - material suggestions, asked once per surface type (label).

Each label sends one representative close-up (its largest region) with a text-only Choice over the
applicable materials and a Noul for weather exposure; the answer applies to every region of that
label. All labels go in one request. Swatch images are not sent: with many options they exceed
Jev's request token limit.
"""

from typing import Any

from PIL.Image import Image
from shapely.geometry import Polygon
from typesafe_sdk import Choice, Noul

from renocore import pixels
from renocore.schemas.entities import OPENING_LABELS, Material, MaterialAdvice, Region
from renocore.vision.guardrails import advice_from_answers
from renocore.vision.jev_adapter import JevClient, jev_image

VERSION = "c4_v2"

FIT_INSTRUCTION = "Which exterior finish best suits the surface outlined in red in this close-up?"
EXPOSED_INSTRUCTION = (
    "Is the surface outlined in red in this close-up directly exposed to rain and sun "
    "(not covered by a roof, slab or balcony)?"
)


def applicable_materials(region: Region, materials: dict[str, Material]) -> list[Material]:
    return [m for m in materials.values() if region.label in m.applicable_labels]


def fit_name(label: str) -> str:
    return f"fit_{label}"


def exposed_name(label: str) -> str:
    return f"exposed_{label}"


def _area(region: Region) -> float:
    poly = Polygon(region.polygon)
    return poly.area if poly.is_valid else poly.buffer(0).area


def representatives(regions: list[Region]) -> dict[str, Region]:
    """Largest region per label (openings excluded)."""
    reps: dict[str, Region] = {}
    for r in regions:
        if r.label in OPENING_LABELS:
            continue
        if r.label not in reps or _area(r) > _area(reps[r.label]):
            reps[r.label] = r
    return reps


def build(
    photo_jpeg: bytes, items: list[tuple[str, bytes, list[Material]]]
) -> tuple[list[Any], dict[str, Any]]:
    """items: (label, crop jpeg, applicable materials)."""
    state = ["Full photo of the building for context:", jev_image(photo_jpeg)]
    questions: dict[str, Any] = {}
    for label, crop, applicable in items:
        crop_image = jev_image(crop)
        if len(applicable) >= 2:
            questions[fit_name(label)] = Choice(
                instructions=[FIT_INSTRUCTION, crop_image],
                criteria={m.id: f"{m.name}: {m.description}" for m in applicable},
            )
        questions[exposed_name(label)] = Noul(instructions=[EXPOSED_INSTRUCTION, crop_image])
    return state, questions


def parse(
    answers: dict[str, dict[str, Any]],
    groups: dict[str, list[Region]],
    applicable: dict[str, list[Material]],
) -> list[MaterialAdvice]:
    out: list[MaterialAdvice] = []
    for label, members in groups.items():
        options = applicable[label]
        fit = answers.get(fit_name(label))
        if fit is not None:
            probs = fit.get("probabilities") or {}
        elif len(options) == 1:
            probs = {options[0].id: 1.0}
        else:
            probs = {}
        exposed_answer = answers.get(exposed_name(label))
        exposed = float(exposed_answer["noul"]) if exposed_answer else None
        for region in members:
            out.append(advice_from_answers(region.id, probs, exposed, options))
    return out


async def run(
    jev: JevClient,
    photo: Image,
    regions: list[Region],
    materials: dict[str, Material],
    seed_dir: Any = None,  # kept for signature compatibility; swatches are no longer sent
) -> list[MaterialAdvice]:
    reps = representatives(regions)
    applicable = {label: applicable_materials(r, materials) for label, r in reps.items()}
    labels = [label for label in reps if applicable[label]]
    if not labels:
        return []
    groups = {label: [r for r in regions if r.label == label] for label in labels}
    items = [
        (
            label,
            pixels.to_jev_jpeg(
                pixels.region_crop(photo, reps[label].polygon, pad=0.25, outline=True)
            ),
            applicable[label],
        )
        for label in labels
    ]
    state, questions = build(pixels.to_jev_jpeg(photo), items)
    result = await jev.ask("C4", state, questions, prompt_version=VERSION)
    return parse(result.answers, groups, applicable)
