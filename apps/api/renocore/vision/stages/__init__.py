"""The six AI calls C1-C6 (architecture.md section 4a): request building, parsing, execution."""

from typing import Any

from renocore.schemas.entities import BoxFraction, BoxResult, ChoiceResult


class AIResponseError(RuntimeError):
    """A model answer was missing or unusable."""


def noul(answers: dict[str, dict[str, Any]], name: str) -> float:
    try:
        return float(answers[name]["noul"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AIResponseError(f"Jev answer {name!r} is missing or not a yes/no answer") from exc


def choice(answers: dict[str, dict[str, Any]], name: str) -> ChoiceResult:
    try:
        a = answers[name]
        return ChoiceResult(
            choice=a["choice"],
            confidence=a.get("confidence"),
            probabilities=a.get("probabilities") or {},
        )
    except (KeyError, TypeError) as exc:
        raise AIResponseError(f"Jev answer {name!r} is missing or not a choice") from exc


def score(answers: dict[str, dict[str, Any]], name: str) -> float:
    try:
        return float(answers[name]["score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AIResponseError(f"Jev answer {name!r} is missing or not a score") from exc


def box(answers: dict[str, dict[str, Any]], name: str) -> BoxResult | None:
    a = answers.get(name)
    if not a or not a.get("box"):
        return None
    b = a["box"]
    return BoxResult(
        box=BoxFraction(top=b["top"], bottom=b["bottom"], left=b["left"], right=b["right"]),
        confidence=a.get("confidence"),
    )
