"""Plain-language descriptions of the automatic steps shown in "How we worked this out".

Each stored AI call (step C1-C6 plus its raw answers) becomes a stage, a title and a one-line
summary of what that step found, written for homeowners.
"""

from collections.abc import Mapping
from typing import Any, Literal

from app.domain.models import FRIENDLY_LABELS, Material

Stage = Literal["photo", "materials", "look"]

STEPS: dict[str, tuple[Stage, str]] = {
    "C1": ("photo", "Checked your photo"),
    "C2": ("photo", "Found the parts of your house"),
    "C3": ("photo", "Double-checked each part"),
    "C4": ("materials", "Suggested materials"),
    "C5": ("look", "Created your new look"),
    "C6": ("look", "Checked the new look"),
}

BUILDING = {
    "independent_house": "an independent house",
    "bungalow": "a bungalow",
    "low_rise_apartment": "a small apartment building",
    "high_rise_apartment": "a tall apartment building",
    "commercial": "a commercial building",
    "not_a_building": "something other than a building",
}
VIEW = {"straight_on": "from the front", "angled": "at an angle", "side": "from the side"}

PLURAL = {
    "wall": ("wall area", "wall areas"),
    "window": ("window", "windows"),
    "door": ("door", "doors"),
    "balcony": ("balcony", "balconies"),
    "pillar": ("pillar", "pillars"),
    "parapet": ("top wall edge", "top wall edges"),
    "railing": ("railing", "railings"),
    "gate": ("gate", "gates"),
    "roof_edge": ("roof edge", "roof edges"),
}
COUNT_ORDER = tuple(PLURAL)


def _choice(output: Mapping[str, Any], key: str) -> str | None:
    answer = output.get(key)
    return answer.get("choice") if isinstance(answer, Mapping) else None


def _noul(output: Mapping[str, Any], key: str) -> float | None:
    answer = output.get(key)
    value = answer.get("noul") if isinstance(answer, Mapping) else None
    return float(value) if isinstance(value, int | float) else None


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _photo(output: Mapping[str, Any]) -> str:
    """e.g. "Looks like an independent house with 2 floors, photographed from the front.
    The main door is visible." """
    building = BUILDING.get(_choice(output, "building_type") or "")
    floors = _choice(output, "floors")
    view = VIEW.get(_choice(output, "view_angle") or "")
    first = f"Looks like {building}" if building else "Checked that the photo can be used"
    if building and floors:
        first += (
            " with 4 or more floors"
            if floors == "4"
            else (f" with {floors} floor" + ("" if floors == "1" else "s"))
        )
    if view:
        first += f", photographed {view}"
    sentences = [first + "."]
    door = _noul(output, "door_visible")
    if door is not None:
        sentences.append(
            "The main door is visible." if door >= 0.7 else "The main door isn’t clearly visible."
        )
    return " ".join(sentences)


def _parts(output: Mapping[str, Any]) -> str:
    counts = output.get("counts")
    if not isinstance(counts, Mapping) or not counts:
        return "Outlined the walls, windows, doors and other parts."
    items = []
    for label in COUNT_ORDER:
        n = counts.get(label)
        if isinstance(n, int) and n > 0:
            one, many = PLURAL[label]
            items.append(f"{n} {one if n == 1 else many}")
    return f"Found {_join(items)}." if items else "No parts were found in this photo."


def _labels(output: Mapping[str, Any], threshold: float) -> str:
    answers = [a for k, a in output.items() if k.startswith("region_") and isinstance(a, Mapping)]
    if not answers:
        return "Confirmed what each part is."
    unsure = sum(1 for a in answers if float(a.get("confidence") or 0) < threshold)
    noun = "part" if len(answers) == 1 else "parts"
    if unsure:
        return f"Confirmed {len(answers)} {noun}; {unsure} marked “Please check” for you."
    return f"Confirmed {len(answers)} {noun}."


def _materials(output: Mapping[str, Any], catalogue: Mapping[str, Material]) -> str:
    picks = []
    for key, answer in output.items():
        if not key.startswith("fit_") or not isinstance(answer, Mapping):
            continue
        label = key.removeprefix("fit_")
        material = catalogue.get(str(answer.get("choice")))
        if material is not None:
            where = FRIENDLY_LABELS.get(label, label.replace("_", " ")).lower()
            picks.append(f"{material.name} for the {where}")
    return f"Top pick: {_join(picks)}." if picks else "Ranked the materials that suit each surface."


def _render(output: Mapping[str, Any]) -> str:
    attempt = output.get("attempt")
    if isinstance(attempt, int) and attempt > 0:
        return f"Tried again with the fixes found in the check (attempt {attempt + 1})."
    return "Applied your chosen materials to the photo."


def _check(output: Mapping[str, Any], threshold: float) -> str:
    issues = []
    openings = _noul(output, "openings_preserved")
    if openings is not None and openings < threshold:
        issues.append("windows or doors may look different")
    structure = _noul(output, "structure_preserved")
    if structure is not None and structure < threshold:
        issues.append("the shape of the house may look different")
    zones = [k for k in output if k.startswith("zone_")]
    weak = [k for k in zones if (_noul(output, k) or 0) < threshold]
    if weak:
        n = len(weak)
        issues.append(f"{n} chosen material{' was' if n == 1 else 's were'} not clearly visible")
    if not issues:
        return "Everything looked right."
    text = _join(issues)
    return text[0].upper() + text[1:] + "."


def starts_run(step: str, output: Mapping[str, Any] | None) -> bool:
    """True for the first attempt of a new-look run (later attempts are automatic redos)."""
    return step == "C5" and isinstance(output, Mapping) and output.get("attempt") == 0


def needs_attention(step: str, summary: str) -> bool:
    """True when the step found something the homeowner should look at."""
    if step == "C6":
        return summary != "Everything looked right."
    if step == "C3":
        return "Please check" in summary
    return False


def describe(
    step: str,
    output: Mapping[str, Any] | None,
    ok: bool,
    catalogue: Mapping[str, Material],
    label_threshold: float,
    qa_threshold: float,
) -> tuple[Stage, str, str]:
    """(stage, title, summary) for one stored AI call."""
    stage, title = STEPS.get(step, ("photo", step.replace("_", " ").capitalize()))
    if not ok:
        return stage, title, "This didn’t work the first time, so we tried again."
    out: Mapping[str, Any] = output or {}
    summary = {
        "C1": lambda: _photo(out),
        "C2": lambda: _parts(out),
        "C3": lambda: _labels(out, label_threshold),
        "C4": lambda: _materials(out, catalogue),
        "C5": lambda: _render(out),
        "C6": lambda: _check(out, qa_threshold),
    }.get(step, lambda: "Done.")()
    return stage, title, summary
