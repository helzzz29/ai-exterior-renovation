"""C1 - whole-photo decisions: ONE Jev request (gate, scale hints, missed surfaces)."""

from typing import Any

from PIL.Image import Image
from typesafe_sdk import Box, Choice, Noul, Score

from renocore import pixels
from renocore.schemas.entities import WholePhotoAnswers
from renocore.vision.jev_adapter import JevClient, jev_image
from renocore.vision.stages import box, choice, noul, score

VERSION = "c1_v1"

BUILDING_TYPES = {
    "independent_house": "independent house",
    "bungalow": "bungalow",
    "low_rise_apartment": "low-rise apartment (up to 4 floors)",
    "high_rise_apartment": "high-rise apartment",
    "commercial": "commercial building",
    "not_a_building": "not a building",
}
VIEW_ANGLES = {
    "straight_on": "straight-on front view",
    "angled": "angled view",
    "side": "side view",
}
FLOORS = {"1": "1 floor", "2": "2 floors", "3": "3 floors", "4": "4 or more floors"}
USABILITY_LEVELS = ["unusable", "poor", "acceptable", "good", "excellent"]


def build(photo_jpeg: bytes) -> tuple[list[Any], dict[str, Any]]:
    state = ["Exterior photo of a building:", jev_image(photo_jpeg)]
    questions: dict[str, Any] = {
        "is_residential_exterior": Noul(
            instructions="Is this a photo of the outside of a residential building?"
        ),
        "building_type": Choice(
            instructions="What type of building is shown?", criteria=BUILDING_TYPES
        ),
        "view_angle": Choice(
            instructions="From which angle is the front of the building photographed?",
            criteria=VIEW_ANGLES,
        ),
        "facade_obstructed": Noul(
            instructions=(
                "Is a large part of the front of the building hidden by trees, vehicles, "
                "walls or objects?"
            )
        ),
        "usability": Score(
            instructions="How suitable is this photo for measuring the front of the building?",
            criteria=USABILITY_LEVELS,
        ),
        "door_visible": Noul(
            instructions="Is the main entrance door of the building fully visible, top to bottom?"
        ),
        "main_door": Box(instructions="the main entrance door of the building"),
        "floors": Choice(
            instructions="How many floors does the building have above the ground?",
            criteria=FLOORS,
        ),
        "railing_visible": Noul(instructions="Is there a balcony or terrace railing visible?"),
        "railing": Box(instructions="the largest balcony or terrace railing"),
        "gate_visible": Noul(instructions="Is there an entrance gate visible?"),
        "gate": Box(instructions="the main entrance gate"),
    }
    return state, questions


def parse(answers: dict[str, dict[str, Any]]) -> WholePhotoAnswers:
    return WholePhotoAnswers(
        is_residential_exterior=noul(answers, "is_residential_exterior"),
        building_type=choice(answers, "building_type"),
        view_angle=choice(answers, "view_angle"),
        facade_obstructed=noul(answers, "facade_obstructed"),
        usability=score(answers, "usability"),
        door_visible=noul(answers, "door_visible"),
        main_door=box(answers, "main_door"),
        floors=choice(answers, "floors"),
        railing_visible=noul(answers, "railing_visible"),
        railing=box(answers, "railing"),
        gate_visible=noul(answers, "gate_visible"),
        gate=box(answers, "gate"),
    )


async def run(jev: JevClient, photo: Image) -> WholePhotoAnswers:
    state, questions = build(pixels.to_jev_jpeg(photo))
    result = await jev.ask("C1", state, questions, prompt_version=VERSION)
    return parse(result.answers)
