"""Table-driven tests for every row of the rule tables (architecture.md 4a)."""

import pytest

from app.ai import apply_labels, photo_verdict, proposed_regions
from app.ai.rules import (
    NOT_IDEAL_PREFIX,
    OPENINGS_FIX,
    STRUCTURE_FIX,
    advice_from_answers,
    qa_from_scores,
    qa_min_score,
)
from app.domain.models import (
    BoxFraction,
    BoxResult,
    ChoiceResult,
    LabelAnswer,
    PhotoCheckResult,
    PhotoIssue,
    WholePhotoAnswers,
    Zone,
)
from tests.unit.ai.conftest import make_material, make_region


def answers(**kw) -> WholePhotoAnswers:
    base = dict(
        is_residential_exterior=0.95,
        building_type=ChoiceResult(choice="independent_house", confidence=0.9),
        view_angle=ChoiceResult(choice="straight_on", confidence=0.9),
        facade_obstructed=0.1,
        usability=3.0,
        door_visible=0.9,
        floors=ChoiceResult(choice="2"),
        railing_visible=0.1,
        gate_visible=0.1,
    )
    for key in ("building_type", "view_angle"):
        if key in kw and isinstance(kw[key], str):
            kw[key] = ChoiceResult(choice=kw[key])
    base.update(kw)
    return WholePhotoAnswers(**base)


def checks(*issues: PhotoIssue) -> PhotoCheckResult:
    return PhotoCheckResult(
        width=1000, height=800, sharpness=200, brightness=0.5, issues=list(issues)
    )


HARD = PhotoIssue(code="blurry", severity="hard", message="This photo is too blurry.")
SOFT = PhotoIssue(code="dim", severity="warn", message="A bit dark.")


# ---------------------------------------------------------------- photo verdict


@pytest.mark.parametrize(
    ("code_issues", "kw", "status", "codes"),
    [
        # reject rows
        ([HARD], {}, "reject", ["blurry"]),
        ([], {"is_residential_exterior": 0.29}, "reject", ["not_residential"]),
        ([], {"building_type": "commercial"}, "reject", ["not_house"]),
        ([], {"building_type": "not_a_building"}, "reject", ["not_house"]),
        ([], {"usability": 0.9}, "reject", ["unusable_photo"]),
        ([HARD, SOFT], {"view_angle": "angled"}, "reject", ["blurry"]),
        # warn rows
        ([], {"is_residential_exterior": 0.3}, "warn", ["uncertain_type"]),
        ([], {"is_residential_exterior": 0.69}, "warn", ["uncertain_type"]),
        ([], {"view_angle": "angled"}, "warn", ["angled_view"]),
        ([], {"view_angle": "side"}, "warn", ["angled_view"]),
        ([], {"facade_obstructed": 0.51}, "warn", ["obstructed"]),
        ([], {"usability": 1.0}, "warn", ["low_quality"]),
        ([], {"usability": 1.99}, "warn", ["low_quality"]),
        ([], {"building_type": "high_rise_apartment"}, "warn", ["high_rise"]),
        ([SOFT], {}, "warn", ["dim"]),
        # pass rows (boundaries)
        ([], {}, "pass", []),
        (
            [],
            {"is_residential_exterior": 0.7, "facade_obstructed": 0.5, "usability": 2.0},
            "pass",
            [],
        ),
        ([], {"building_type": "bungalow"}, "pass", []),
        ([], {"building_type": "low_rise_apartment"}, "pass", []),
    ],
)
def test_photo_verdict(code_issues, kw, status, codes):
    verdict = photo_verdict(checks(*code_issues), answers(**kw))
    assert verdict.status == status
    assert [i.code for i in verdict.issues] == codes
    for issue in verdict.issues:
        assert issue.message and "confidence" not in issue.message.lower()


def test_angled_message_is_plain_language():
    verdict = photo_verdict(checks(), answers(view_angle="angled"))
    assert verdict.issues[0].message == (
        "The photo is taken at an angle, so sizes may be less accurate. "
        "A straight-on photo works best."
    )
    assert verdict.issues[0].severity == "warn"


# ---------------------------------------------------------------- labels


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        # (label, confidence) -> (kept, label, confidence, needs_check)
        (("pillar", 0.9), (True, "pillar", 0.9, False)),
        (("pillar", 0.6), (True, "pillar", 0.6, False)),
        (("pillar", 0.59), (True, "pillar", 0.59, True)),
        (("window", 0.45), (True, "window", 0.45, True)),
        (("not_building", 0.6), (False, None, None, None)),
        (("not_building", 0.95), (False, None, None, None)),
        (("not_building", 0.5), (True, "wall", 0.3, True)),
        (None, (True, "wall", None, False)),
    ],
)
def test_apply_labels(answer, expected):
    region = make_region("r1", "wall")
    answers_ = {}
    if answer is not None:
        label, conf = answer
        answers_["r1"] = LabelAnswer(
            label=label, confidence=conf, probabilities={label: conf, "wall": 0.3}
        )
    out = apply_labels([region], answers_, threshold=0.6)
    kept, label, conf, needs_check = expected
    if not kept:
        assert out == []
        return
    assert len(out) == 1
    assert out[0].label == label
    assert out[0].label_confidence == conf
    assert out[0].needs_check is needs_check
    assert out[0].id == "r1"


def test_apply_labels_keeps_order_and_other_fields():
    regions = [make_region("a", "wall", source="user"), make_region("b", "window")]
    out = apply_labels(regions, {"b": LabelAnswer(label="door", confidence=0.8)}, 0.6)
    assert [r.id for r in out] == ["a", "b"]
    assert out[0].source == "user"
    assert out[1].label == "door"


# ---------------------------------------------------------------- proposals


def box(top, bottom, left, right) -> BoxResult:
    return BoxResult(box=BoxFraction(top=top, bottom=bottom, left=left, right=right))


RAIL_BOX = box(0.1, 0.2, 0.1, 0.5)  # px (100,100)-(500,200) on 1000x1000


@pytest.mark.parametrize(
    ("presence", "rail_box", "existing", "expected"),
    [
        (0.6, RAIL_BOX, [], 1),
        (0.59, RAIL_BOX, [], 0),
        (0.9, None, [], 0),
        # same label overlapping heavily -> no proposal
        (0.9, RAIL_BOX, [make_region("x", "railing", (100, 100, 500, 200))], 0),
        # same label, IoU exactly 0.25 (<= 0.3) -> proposal
        (0.9, RAIL_BOX, [make_region("x", "railing", (100, 100, 200, 200))], 1),
        # different label overlapping -> still proposed
        (0.9, RAIL_BOX, [make_region("x", "wall", (100, 100, 500, 200))], 1),
        # degenerate box
        (0.9, box(0.1, 0.1, 0.1, 0.5), [], 0),
    ],
)
def test_proposed_railing(presence, rail_box, existing, expected):
    a = answers(railing_visible=presence, railing=rail_box)
    out = proposed_regions(a, existing, 1000, 1000)
    assert len(out) == expected
    if expected:
        r = out[0]
        assert r.label == "railing" and r.source == "jev_box" and r.proposed
        assert r.polygon == [(100, 100), (500, 100), (500, 200), (100, 200)]
        assert r.id.startswith("railing-")


def test_proposed_gate_and_railing_together():
    a = answers(
        railing_visible=0.8, railing=RAIL_BOX, gate_visible=0.7, gate=box(0.7, 0.95, 0.0, 0.3)
    )
    out = proposed_regions(a, [], 1000, 1000)
    assert [r.label for r in out] == ["railing", "gate"]


# ---------------------------------------------------------------- material advice


@pytest.fixture
def wall_materials():
    return [
        make_material("paint", ["wall"], weather_resistance="medium"),
        make_material("stone", ["wall"], weather_resistance="high"),
        make_material(
            "lime",
            ["wall"],
            weather_resistance="low",
            maintenance="Needs frequent maintenance in rain.",
        ),
    ]


@pytest.mark.parametrize(
    ("probs", "exposed", "recommended", "not_ideal"),
    [
        ({"paint": 0.2, "stone": 0.5, "lime": 0.3}, 0.3, ["stone", "lime"], []),
        ({"paint": 0.2, "stone": 0.5, "lime": 0.3}, 0.6, ["stone", "paint"], ["lime"]),
        ({"paint": 0.2, "stone": 0.5, "lime": 0.3}, 0.59, ["stone", "lime"], []),
        ({"paint": 0.2, "stone": 0.5, "lime": 0.3}, None, ["stone", "lime"], []),
        ({"paint": 0.5, "stone": 0.5, "lime": 0.0}, 0.0, ["paint", "stone"], []),  # tie: order
        ({}, 0.9, [], ["lime"]),
        ({"paint": 0.9, "unknown": 0.1}, 0.0, ["paint"], []),
    ],
)
def test_advice_rules(wall_materials, probs, exposed, recommended, not_ideal):
    advice = advice_from_answers("r1", probs, exposed, wall_materials)
    assert advice.recommended == recommended
    assert sorted(advice.not_ideal) == not_ideal
    assert advice.exposed == exposed
    assert "unknown" not in advice.probabilities
    for reason in advice.not_ideal.values():
        assert reason == f"{NOT_IDEAL_PREFIX} Needs frequent maintenance in rain."


# ---------------------------------------------------------------- QA


@pytest.fixture
def zones():
    return [
        Zone(region_ids=["a"], material_id="stone", color_name="red", rgb=(255, 0, 0)),
        Zone(region_ids=["b"], material_id="glass", color_name="yellow", rgb=(255, 255, 0)),
    ]


@pytest.fixture
def qa_materials():
    return {
        "stone": make_material("stone", ["wall"], name="Natural stone cladding"),
        "glass": make_material("glass", ["railing"], name="Toughened glass railing"),
    }


@pytest.mark.parametrize(
    ("openings", "structure", "red", "yellow", "passed", "failed"),
    [
        (0.9, 0.9, 0.9, 0.9, True, []),
        (0.6, 0.6, 0.6, 0.6, True, []),
        (0.59, 0.9, 0.9, 0.9, False, [OPENINGS_FIX]),
        (0.9, 0.2, 0.9, 0.9, False, [STRUCTURE_FIX]),
        (0.9, 0.9, 0.9, 0.3, False, ["The area shown in yellow must be toughened glass railing."]),
        (
            0.1,
            0.1,
            0.1,
            None,
            False,
            [
                OPENINGS_FIX,
                STRUCTURE_FIX,
                "The area shown in red must be natural stone cladding.",
                "The area shown in yellow must be toughened glass railing.",
            ],
        ),
    ],
)
def test_qa_rule(zones, qa_materials, openings, structure, red, yellow, passed, failed):
    scores = {"red": red}
    if yellow is not None:
        scores["yellow"] = yellow
    qa = qa_from_scores(openings, structure, scores, zones, qa_materials, 0.6)
    assert qa.passed is passed
    assert qa.failed_checks == failed
    assert qa.zones == scores


def test_qa_fix_text_examples_and_min_score(zones, qa_materials):
    assert OPENINGS_FIX == "Keep every window and door exactly as in the original photo."
    qa = qa_from_scores(0.7, 0.8, {"red": 0.4, "yellow": 0.9}, zones, qa_materials, 0.6)
    assert qa_min_score(qa) == 0.4
    unknown = Zone(region_ids=["c"], material_id="nope", color_name="blue", rgb=(0, 0, 255))
    qa2 = qa_from_scores(0.9, 0.9, {}, [unknown], qa_materials, 0.6)
    assert qa2.failed_checks == ["The area shown in blue must be the chosen material."]


@pytest.mark.parametrize(
    ("probs", "warned"),
    [
        ({"straight_on": 0.45, "angled": 0.55, "side": 0.0}, False),  # live case: near-frontal
        ({"straight_on": 0.35, "angled": 0.65}, True),
        ({"straight_on": 0.3, "angled": 0.4, "side": 0.3}, True),
        ({"straight_on": 0.36, "angled": 0.34, "side": 0.30}, False),
        ({"straight_on": 0.9, "side": 0.1}, False),
    ],
)
def test_view_angle_uses_probability_mass(probs, warned):
    top = max(probs, key=probs.get)
    view = ChoiceResult(choice=top, confidence=probs[top], probabilities=probs)
    verdict = photo_verdict(checks(), answers(view_angle=view))
    assert ("angled_view" in [i.code for i in verdict.issues]) is warned
