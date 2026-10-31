"""Jev calls C1, C3, C4, C6: request snapshots (question names/types/criteria) and parsing."""

import pytest

from app.ai.cache import sha256_bytes
from app.ai.jev_client import describe
from app.ai.steps import AIResponseError, check, labels, whole_photo
from app.ai.steps import advice as advice_step
from app.domain.models import Zone
from tests.unit.ai.conftest import FakeJevSDK, make_jev, make_photo, make_region


def img(data: bytes) -> dict:
    return {"image": sha256_bytes(data)}


# ---------------------------------------------------------------- C1


def test_c1_request_snapshot():
    state, questions = whole_photo.build(b"PHOTO")
    assert describe(state) == ["Exterior photo of a building:", img(b"PHOTO")]
    snap = describe(questions)
    assert list(snap) == [
        "is_residential_exterior",
        "building_type",
        "view_angle",
        "facade_obstructed",
        "usability",
        "door_visible",
        "main_door",
        "floors",
        "railing_visible",
        "railing",
        "gate_visible",
        "gate",
    ]
    assert {k: v["type"] for k, v in snap.items()} == {
        "is_residential_exterior": "noul",
        "building_type": "choice",
        "view_angle": "choice",
        "facade_obstructed": "noul",
        "usability": "score",
        "door_visible": "noul",
        "main_door": "box",
        "floors": "choice",
        "railing_visible": "noul",
        "railing": "box",
        "gate_visible": "noul",
        "gate": "box",
    }
    assert snap["is_residential_exterior"]["instructions"] == (
        "Is this a photo of the outside of a residential building?"
    )
    assert snap["building_type"]["criteria"] == {
        "independent_house": "independent house",
        "bungalow": "bungalow",
        "low_rise_apartment": "low-rise apartment (up to 4 floors)",
        "high_rise_apartment": "high-rise apartment",
        "commercial": "commercial building",
        "not_a_building": "not a building",
    }
    assert snap["view_angle"]["criteria"] == {
        "straight_on": "straight-on front view",
        "angled": "angled view",
        "side": "side view",
    }
    assert snap["usability"]["criteria"] == ["unusable", "poor", "acceptable", "good", "excellent"]
    assert snap["floors"]["criteria"] == {
        "1": "1 floor",
        "2": "2 floors",
        "3": "3 floors",
        "4": "4 or more floors",
    }
    assert snap["main_door"] == {
        "type": "box",
        "instructions": "the main entrance door of the building",
    }
    assert snap["railing"]["instructions"] == "the largest balcony or terrace railing"
    assert snap["gate"]["instructions"] == "the main entrance gate"


async def test_c1_one_request_and_parse(recorder):
    sdk = FakeJevSDK(
        {"usability": {"score": 2.7}, "floors": {"choice": "4"}, "railing_visible": {"noul": 0.2}}
    )
    jev = make_jev(sdk, recorder)
    result = await whole_photo.run(jev, make_photo())
    assert len(sdk.calls) == 1
    assert result.usability == 2.7
    assert result.floors.choice == "4"
    assert result.building_type.choice == "independent_house"
    assert result.main_door is not None and result.main_door.box.top == 0.6
    assert result.main_door.confidence == 0.85
    assert result.railing_visible == 0.2
    rec = recorder.calls[0]
    assert rec.step == "C1" and rec.provider == "jev" and rec.prompt_version == "c1_v1"
    assert rec.input_tokens == 1000 and rec.cost_usd == pytest.approx(0.000042)
    assert rec.cached is False and rec.attempts == 1


def test_c1_parse_missing_answer_raises():
    with pytest.raises(AIResponseError, match="is_residential_exterior"):
        whole_photo.parse({})


def test_parse_helpers_errors():
    from app.ai.steps import box, choice, score

    with pytest.raises(AIResponseError):
        choice({"x": {"type": "noul"}}, "x")
    with pytest.raises(AIResponseError):
        score({"x": {"type": "noul"}}, "x")
    assert box({}, "x") is None


# ---------------------------------------------------------------- C3


def test_c3_request_snapshot():
    r1, r2 = make_region("r1", "wall"), make_region("a/b", "pillar")
    state, questions = labels.build(b"PHOTO", [(r1, b"C1"), (r2, b"C2")])
    assert describe(state) == ["Full photo of the building for context:", img(b"PHOTO")]
    criteria = {
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
    assert describe(questions) == {
        "region_r1": {
            "type": "choice",
            "criteria": criteria,
            "instructions": [
                "What is the part of the building outlined in red in this close-up?",
                img(b"C1"),
            ],
        },
        "region_a_b": {
            "type": "choice",
            "criteria": criteria,
            "instructions": [
                "What is the part of the building outlined in red in this close-up?",
                img(b"C2"),
            ],
        },
    }


async def test_c3_batches_of_20_and_parse(recorder):
    regions = [make_region(f"r{i}", "wall") for i in range(45)]
    sdk = FakeJevSDK({"region_r3": {"choice": "not_building", "confidence": 0.7}})
    out = await labels.run(make_jev(sdk, recorder), make_photo(), regions)
    assert [len(q) for _, q in sdk.calls] == [20, 20, 5]
    assert len(out) == 45
    assert out["r0"].label == "wall" and out["r0"].confidence == 0.8
    assert out["r3"].label == "not_building"
    assert len(recorder.calls) == 3


async def test_c3_empty_and_bad_label():
    assert await labels.run(make_jev(FakeJevSDK()), make_photo(), []) == {}
    with pytest.raises(AIResponseError):
        labels.parse({"region_r1": {"choice": "spaceship"}}, [make_region("r1", "wall")])
    # region without an answer is simply absent
    assert labels.parse({}, [make_region("r1", "wall")]) == {}


# ---------------------------------------------------------------- C4


def test_c4_request_snapshot(materials):
    wall = make_region("w1", "wall")
    rail = make_region("rl", "railing")
    applicable_wall = advice_step.applicable_materials(wall, materials)
    applicable_rail = advice_step.applicable_materials(rail, materials)
    state, questions = advice_step.build(
        b"PHOTO", [("wall", b"CW", applicable_wall), ("railing", b"CR", applicable_rail)]
    )
    assert describe(state) == ["Full photo of the building for context:", img(b"PHOTO")]
    snap = describe(questions)
    assert list(snap) == ["fit_wall", "exposed_wall", "exposed_railing"]  # one option: no Choice
    assert snap["fit_wall"] == {
        "type": "choice",
        "instructions": [advice_step.FIT_INSTRUCTION, img(b"CW")],
        "criteria": {
            "paint": "Beige texture paint: paint finish",
            "stone": "Natural stone cladding: stone finish",
            "lime": "Lime wash: lime finish",
        },
    }
    assert snap["exposed_wall"] == {
        "type": "noul",
        "instructions": [advice_step.EXPOSED_INSTRUCTION, img(b"CW")],
    }
    assert "rain and sun" in advice_step.EXPOSED_INSTRUCTION


async def test_c4_one_request_per_label_group(materials, settings, recorder):
    regions = [make_region(f"w{i}", "wall") for i in range(12)]
    regions += [
        make_region("win", "window"),
        make_region("rl", "railing"),
        make_region("rf", "roof_edge"),
    ]
    sdk = FakeJevSDK(
        {
            "fit_wall": {
                "choice": "lime",
                "probabilities": {"paint": 0.1, "stone": 0.3, "lime": 0.6},
            },
            "exposed_wall": {"noul": 0.8},
        }
    )
    out = await advice_step.run(
        make_jev(sdk, recorder), make_photo(), regions, materials, settings.seed_dir
    )
    assert len(sdk.calls) == 1  # all surface types in a single request
    by_id = {a.region_id: a for a in out}
    assert set(by_id) == {f"w{i}" for i in range(12)} | {"rl"}  # window/roof_edge skipped
    for i in range(12):  # every wall shares the wall answer
        assert by_id[f"w{i}"].recommended == ["stone", "paint"]
        assert list(by_id[f"w{i}"].not_ideal) == ["lime"]
    assert by_id["rl"].recommended == ["glass"]
    _, questions = sdk.calls[0]
    assert set(questions) == {"fit_wall", "exposed_wall", "exposed_railing"}
    # text-only options: no swatch images in the request
    assert all(isinstance(v, str) for v in questions["fit_wall"].criteria.values())


def test_c4_representative_is_largest_region():
    small = make_region("s", "wall")
    big = small.model_copy(update={"id": "b", "polygon": [(0, 0), (500, 0), (500, 400), (0, 400)]})
    reps = advice_step.representatives([small, big, make_region("d", "door")])
    assert reps == {"wall": big}


async def test_c4_nothing_to_ask(materials, settings):
    sdk = FakeJevSDK()
    out = await advice_step.run(
        make_jev(sdk), make_photo(), [make_region("d", "door")], materials, settings.seed_dir
    )
    assert out == [] and sdk.calls == []


def test_c4_parse_without_answers(materials):
    wall = make_region("w", "wall")
    out = advice_step.parse(
        {}, {"wall": [wall]}, {"wall": advice_step.applicable_materials(wall, materials)}
    )
    assert out[0].recommended == [] and out[0].exposed is None


# ---------------------------------------------------------------- C6


@pytest.fixture
def zones():
    return [
        Zone(region_ids=["a"], material_id="stone", color_name="red", rgb=(255, 0, 0)),
        Zone(region_ids=["b"], material_id="glass", color_name="yellow", rgb=(255, 255, 0)),
    ]


def test_c6_request_snapshot(zones, materials):
    state, questions = check.build(
        b"O", b"R", b"Z", zones, materials, {"stone": b"S1", "glass": b"S2"}
    )
    assert describe(state) == [
        "Original photo:",
        img(b"O"),
        "Redesigned photo:",
        img(b"R"),
        "Zone map:",
        img(b"Z"),
    ]
    assert describe(questions) == {
        "openings_preserved": {
            "type": "noul",
            "instructions": (
                "Are all windows and doors in the redesigned photo in the same positions, "
                "sizes and "
                "number as in the original?"
            ),
        },
        "structure_preserved": {
            "type": "noul",
            "instructions": (
                "Does the redesigned photo keep the same building shape, roofline and number of "
                "floors?"
            ),
        },
        "zone_red": {
            "type": "noul",
            "instructions": [
                "In the redesigned photo, is the area shown in red in the zone map finished with "
                "Natural stone cladding, like this sample?",
                img(b"S1"),
            ],
        },
        "zone_yellow": {
            "type": "noul",
            "instructions": [
                "In the redesigned photo, is the area shown in yellow in the zone map "
                "finished with "
                "Toughened glass railing, like this sample?",
                img(b"S2"),
            ],
        },
    }


def test_c6_without_swatch_uses_text_only(zones, materials):
    _, questions = check.build(b"O", b"R", b"Z", zones, materials, {})
    assert isinstance(questions["zone_red"].instructions, str)


@pytest.mark.parametrize(("yellow", "passed"), [(0.9, True), (0.4, False)])
async def test_c6_run(zones, materials, settings, yellow, passed):
    sdk = FakeJevSDK({"zone_yellow": {"noul": yellow}})
    photo = make_photo()
    qa = await check.run(
        make_jev(sdk), photo, photo, photo, zones, materials, settings.seed_dir, 0.6
    )
    assert len(sdk.calls) == 1
    assert qa.passed is passed
    assert qa.zones == {"red": 0.9, "yellow": yellow}
    if not passed:
        assert qa.failed_checks == ["The area shown in yellow must be toughened glass railing."]
