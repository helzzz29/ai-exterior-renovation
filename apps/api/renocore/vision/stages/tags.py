"""C3 - region labels: one Jev Choice per region crop, up to 20 regions per request."""

import asyncio
import re
from typing import Any

from PIL.Image import Image
from typesafe_sdk import Choice

from renocore import pixels
from renocore.schemas.entities import LabelAnswer, Region
from renocore.vision.jev_adapter import JevClient, jev_image
from renocore.vision.stages import AIResponseError

VERSION = "c3_v1"
BATCH_SIZE = 20

LABEL_CRITERIA = {
    "wall": "wall",
    "window": "window",
    "door": "door",
    "balcony": "balcony",
    "pillar": "pillar or column",
    "parapet": "parapet (low wall along the roof edge)",
    "railing": "railing",
    "gate": "gate",
    "roof_edge": "roof edge or fascia",
    "not_building": "not part of the building",
}
INSTRUCTION = "What is the part of the building outlined in red in this close-up?"


def question_name(region_id: str) -> str:
    return "region_" + re.sub(r"[^A-Za-z0-9_-]", "_", region_id)


def batches(regions: list[Region], size: int = BATCH_SIZE) -> list[list[Region]]:
    return [regions[i : i + size] for i in range(0, len(regions), size)]


def build(photo_jpeg: bytes, crops: list[tuple[Region, bytes]]) -> tuple[list[Any], dict[str, Any]]:
    state = ["Full photo of the building for context:", jev_image(photo_jpeg)]
    questions: dict[str, Any] = {}
    for region, crop in crops:
        questions[question_name(region.id)] = Choice(
            instructions=[INSTRUCTION, jev_image(crop)], criteria=LABEL_CRITERIA
        )
    return state, questions


def parse(answers: dict[str, dict[str, Any]], regions: list[Region]) -> dict[str, LabelAnswer]:
    out: dict[str, LabelAnswer] = {}
    for region in regions:
        a = answers.get(question_name(region.id))
        if a is None:
            continue  # no answer: apply_labels keeps the Gemini label
        if a.get("choice") not in LABEL_CRITERIA:
            raise AIResponseError(f"Unexpected label {a.get('choice')!r} for region {region.id}")
        out[region.id] = LabelAnswer(
            label=a["choice"],
            confidence=float(a.get("confidence") or 0.0),
            probabilities=a.get("probabilities") or {},
        )
    return out


async def run(jev: JevClient, photo: Image, regions: list[Region]) -> dict[str, LabelAnswer]:
    if not regions:
        return {}
    photo_jpeg = pixels.to_jev_jpeg(photo)

    async def one(batch: list[Region]) -> dict[str, LabelAnswer]:
        crops = [
            (r, pixels.to_jev_jpeg(pixels.region_crop(photo, r.polygon, pad=0.25, outline=True)))
            for r in batch
        ]
        state, questions = build(photo_jpeg, crops)
        result = await jev.ask("C3", state, questions, prompt_version=VERSION)
        return parse(result.answers, batch)

    merged: dict[str, LabelAnswer] = {}
    for part in await asyncio.gather(*(one(b) for b in batches(regions))):
        merged.update(part)
    return merged
