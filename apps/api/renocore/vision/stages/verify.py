"""C6 - design check: ONE Jev request comparing original, redesign and zone map."""

from pathlib import Path
from typing import Any

from PIL.Image import Image
from typesafe_sdk import Noul

from renocore import pixels
from renocore.schemas.entities import Material, QAResult, Zone
from renocore.vision.guardrails import qa_from_scores
from renocore.vision.jev_adapter import JevClient, jev_image
from renocore.vision.payloads import load_swatch
from renocore.vision.stages import noul

VERSION = "c6_v1"

OPENINGS_Q = (
    "Are all windows and doors in the redesigned photo in the same positions, sizes and number "
    "as in the original?"
)
STRUCTURE_Q = (
    "Does the redesigned photo keep the same building shape, roofline and number of floors?"
)


def zone_question_name(zone: Zone) -> str:
    return "zone_" + zone.color_name.replace(" ", "_")


def zone_instruction(zone: Zone, material: Material | None) -> str:
    name = material.name if material else "the chosen material"
    return (
        f"In the redesigned photo, is the area shown in {zone.color_name} in the zone map "
        f"finished with {name}, like this sample?"
    )


def build(
    original_jpeg: bytes,
    result_jpeg: bytes,
    zone_map_jpeg: bytes,
    zones: list[Zone],
    materials: dict[str, Material],
    swatches: dict[str, bytes],
) -> tuple[list[Any], dict[str, Any]]:
    state = [
        "Original photo:",
        jev_image(original_jpeg),
        "Redesigned photo:",
        jev_image(result_jpeg),
        "Zone map:",
        jev_image(zone_map_jpeg),
    ]
    questions: dict[str, Any] = {
        "openings_preserved": Noul(instructions=OPENINGS_Q),
        "structure_preserved": Noul(instructions=STRUCTURE_Q),
    }
    for zone in zones:
        text = zone_instruction(zone, materials.get(zone.material_id))
        swatch = swatches.get(zone.material_id)
        questions[zone_question_name(zone)] = Noul(
            instructions=[text, jev_image(swatch)] if swatch else text
        )
    return state, questions


def parse(
    answers: dict[str, dict[str, Any]],
    zones: list[Zone],
    materials: dict[str, Material],
    threshold: float,
) -> QAResult:
    zone_scores = {z.color_name: noul(answers, zone_question_name(z)) for z in zones}
    return qa_from_scores(
        noul(answers, "openings_preserved"),
        noul(answers, "structure_preserved"),
        zone_scores,
        zones,
        materials,
        threshold,
    )


async def run(
    jev: JevClient,
    original: Image,
    result: Image,
    zone_map: Image,
    zones: list[Zone],
    materials: dict[str, Material],
    seed_dir: Path,
    threshold: float,
) -> QAResult:
    swatches = {
        z.material_id: pixels.to_jev_jpeg(load_swatch(seed_dir, materials[z.material_id]))
        for z in zones
        if z.material_id in materials
    }
    state, questions = build(
        pixels.to_jev_jpeg(original),
        pixels.to_jev_jpeg(result),
        pixels.to_jev_jpeg(zone_map),
        zones,
        materials,
        swatches,
    )
    answer = await jev.ask("C6", state, questions, prompt_version=VERSION)
    return parse(answer.answers, zones, materials, threshold)
