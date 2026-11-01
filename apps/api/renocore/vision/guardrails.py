"""Pure decision rules on top of model answers (architecture.md section 4a). No I/O."""

from uuid import uuid4

from renocore import pixels
from renocore.schemas.entities import (
    LabelAnswer,
    Material,
    MaterialAdvice,
    PhotoCheckResult,
    PhotoIssue,
    PhotoVerdict,
    QAResult,
    Region,
    WholePhotoAnswers,
    Zone,
)

# ---------------------------------------------------------------- photo verdict (C1)

REJECT_BUILDING_TYPES = frozenset({"commercial", "not_a_building"})
STRAIGHT_ON = "straight_on"
ANGLED_WARN_PROBABILITY = 0.65  # P(angled) + P(side); Jev splits near-frontal photos ~50/50

ISSUE_MESSAGES: dict[str, str] = {
    "not_residential": (
        "This doesn't look like the outside of a house. "
        "Please upload a photo of the front of your house, taken from outside."
    ),
    "not_house": (
        "This looks like a shop, office or something other than a home. "
        "Please upload a photo of the front of your house."
    ),
    "unusable_photo": (
        "We can't measure your house from this photo. Please take a clear photo of the whole "
        "front of the house in daylight, standing across the road if you can."
    ),
    "uncertain_type": (
        "We're not completely sure this is a house. If it is, you can continue, "
        "or upload a clearer photo of the front."
    ),
    "angled_view": (
        "The photo is taken at an angle, so sizes may be less accurate. "
        "A straight-on photo works best."
    ),
    "obstructed": (
        "Part of the front of the house is hidden, for example by trees, vehicles or a wall, "
        "so some parts may be missed. A clear view of the front works best."
    ),
    "low_quality": (
        "The photo quality is below average, so sizes may be less accurate. "
        "A sharp, well-lit photo of the whole front works best."
    ),
    "high_rise": (
        "This looks like a tall apartment building. Estimates work best for houses "
        "and low-rise buildings, so treat the results as a rough guide."
    ),
}


def _issue(code: str, severity: str) -> PhotoIssue:
    return PhotoIssue(code=code, severity=severity, message=ISSUE_MESSAGES[code])  # type: ignore[arg-type]


def is_angled(answers: WholePhotoAnswers) -> bool:
    probs = answers.view_angle.probabilities
    if probs:
        return probs.get("angled", 0.0) + probs.get("side", 0.0) >= ANGLED_WARN_PROBABILITY
    return answers.view_angle.choice != STRAIGHT_ON


def photo_verdict(checks: PhotoCheckResult, answers: WholePhotoAnswers) -> PhotoVerdict:
    """Reject / warn / pass from code checks plus C1 answers.

    Reject: any hard code issue, is_residential_exterior < 0.3, building type commercial or not a
    building, usability < 1.0. Warn: is_residential_exterior in [0.3, 0.7),
    P(angled) + P(side) >= 0.65 (top choice if no probabilities),
    facade_obstructed > 0.5, usability < 2.0, high-rise, or any warning from the code checks.
    On reject only the blocking issues are returned (one clear message, no clutter).
    """
    hard = [i for i in checks.issues if i.severity == "hard"]
    warn = [i for i in checks.issues if i.severity == "warn"]

    if answers.is_residential_exterior < 0.3:
        hard.append(_issue("not_residential", "hard"))
    if answers.building_type.choice in REJECT_BUILDING_TYPES:
        hard.append(_issue("not_house", "hard"))
    if answers.usability < 1.0:
        hard.append(_issue("unusable_photo", "hard"))
    if hard:
        return PhotoVerdict(status="reject", issues=hard)

    if answers.is_residential_exterior < 0.7:
        warn.append(_issue("uncertain_type", "warn"))
    if is_angled(answers):
        warn.append(_issue("angled_view", "warn"))
    if answers.facade_obstructed > 0.5:
        warn.append(_issue("obstructed", "warn"))
    if answers.usability < 2.0:
        warn.append(_issue("low_quality", "warn"))
    if answers.building_type.choice == "high_rise_apartment":
        warn.append(_issue("high_rise", "warn"))
    if warn:
        return PhotoVerdict(status="warn", issues=warn)
    return PhotoVerdict(status="pass", issues=[])


# ---------------------------------------------------------------- labels (C3)


def apply_labels(
    regions: list[Region], answers: dict[str, LabelAnswer], threshold: float
) -> list[Region]:
    """Final label = Jev label with its confidence; "Please check" below `threshold`.

    - No answer for a region: keep it unchanged (Gemini label stays).
    - "not part of the building" with confidence >= threshold: region dropped.
    - "not part of the building" below threshold: keep the current label, flag for checking.
    """
    out: list[Region] = []
    for region in regions:
        answer = answers.get(region.id)
        if answer is None:
            out.append(region)
            continue
        if answer.label == "not_building":
            if answer.confidence >= threshold:
                continue
            out.append(
                region.model_copy(
                    update={
                        "label_confidence": answer.probabilities.get(region.label),
                        "needs_check": True,
                    }
                )
            )
            continue
        out.append(
            region.model_copy(
                update={
                    "label": answer.label,
                    "label_confidence": answer.confidence,
                    "needs_check": answer.confidence < threshold,
                }
            )
        )
    return out


# ---------------------------------------------------------------- proposals (C1 boxes)

PROPOSAL_PRESENCE = 0.6
PROPOSAL_MAX_IOU = 0.3


def proposed_regions(
    answers: WholePhotoAnswers, existing: list[Region], width: int, height: int
) -> list[Region]:
    """Railing / gate boxes from C1 that no existing same-label region already covers."""
    proposals: list[Region] = []
    for label, presence, box in (
        ("railing", answers.railing_visible, answers.railing),
        ("gate", answers.gate_visible, answers.gate),
    ):
        if box is None or presence < PROPOSAL_PRESENCE:
            continue
        px = pixels.fraction_box_to_px(box.box, width, height)
        if px.x1 - px.x0 < 1 or px.y1 - px.y0 < 1:
            continue
        same = [r for r in existing if r.label == label]
        overlaps = [pixels.box_iou(px, pixels.polygon_box(r.polygon)) for r in same]
        if any(iou > PROPOSAL_MAX_IOU for iou in overlaps):
            continue
        proposals.append(
            Region(
                id=f"{label}-{uuid4().hex[:8]}",
                label=label,  # type: ignore[arg-type]
                polygon=pixels.box_polygon(px),
                source="jev_box",
                label_confidence=presence,
                proposed=True,
            )
        )
    return proposals


# ---------------------------------------------------------------- material advice (C4)

EXPOSED_THRESHOLD = 0.6
NOT_IDEAL_PREFIX = "Not ideal here: this part gets direct rain and sun."
RECOMMENDED_COUNT = 2


def advice_from_answers(
    region_id: str,
    probabilities: dict[str, float],
    exposed: float | None,
    applicable: list[Material],
) -> MaterialAdvice:
    """Not ideal: exposed >= 0.6 and low weather resistance (reason from catalogue maintenance).

    Recommended: the two highest-probability materials that are not marked "not ideal here"
    (a material is never both recommended and not ideal).
    """
    ids = {m.id for m in applicable}
    probs = {k: v for k, v in probabilities.items() if k in ids}
    not_ideal: dict[str, str] = {}
    if exposed is not None and exposed >= EXPOSED_THRESHOLD:
        for m in applicable:
            if m.weather_resistance == "low":
                not_ideal[m.id] = f"{NOT_IDEAL_PREFIX} {m.maintenance}"
    order = {m.id: i for i, m in enumerate(applicable)}
    ranked = sorted(
        (mid for mid in probs if mid not in not_ideal),
        key=lambda mid: (-probs[mid], order[mid]),
    )
    return MaterialAdvice(
        region_id=region_id,
        recommended=ranked[:RECOMMENDED_COUNT],
        not_ideal=not_ideal,
        exposed=exposed,
        probabilities=probs,
    )


# ---------------------------------------------------------------- render QA (C6)

OPENINGS_FIX = "Keep every window and door exactly as in the original photo."
STRUCTURE_FIX = (
    "Keep the building's shape, roofline and number of floors exactly as in the original photo."
)


def zone_fix(zone: Zone, materials: dict[str, Material]) -> str:
    material = materials.get(zone.material_id)
    name = material.name.lower() if material else "the chosen material"
    return f"The area shown in {zone.color_name} must be {name}."


def qa_from_scores(
    openings: float,
    structure: float,
    zone_scores: dict[str, float],
    zones: list[Zone],
    materials: dict[str, Material],
    threshold: float,
) -> QAResult:
    """A render passes when every answer >= threshold; failures become plain fix instructions."""
    failed: list[str] = []
    if openings < threshold:
        failed.append(OPENINGS_FIX)
    if structure < threshold:
        failed.append(STRUCTURE_FIX)
    for zone in zones:
        score = zone_scores.get(zone.color_name)
        if score is None or score < threshold:
            failed.append(zone_fix(zone, materials))
    return QAResult(
        openings_preserved=openings,
        structure_preserved=structure,
        zones=dict(zone_scores),
        passed=not failed,
        failed_checks=failed,
    )


def qa_min_score(qa: QAResult) -> float:
    return min([qa.openings_preserved, qa.structure_preserved, *qa.zones.values()])
