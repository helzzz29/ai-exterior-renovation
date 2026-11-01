from types import SimpleNamespace

from renocore.operations.budgets import floors_from_answer
from renocore.operations.lifecycle import _area, _keep_confirmation, _norm_polygon
from renocore.operations.photos import sniff
from renocore.operations.signatures import fingerprint
from renocore.schemas.entities import (
    ChoiceResult,
    Confidence,
    ScaleMethod,
    ScaleResult,
    WholePhotoAnswers,
)
from renocore.settings import Settings


def test_fingerprint_is_stable_and_order_insensitive_for_dicts() -> None:
    assert fingerprint({"a": 1, "b": [1.0000001, 2]}) == fingerprint({"b": [1.0, 2], "a": 1})
    assert fingerprint("x") != fingerprint("y")
    scale = ScaleResult(
        ft_per_px=0.1, method=ScaleMethod.door, confidence=Confidence.medium, explanation="e"
    )
    assert fingerprint(scale) == fingerprint(scale.model_copy())


def test_sniff_by_signature() -> None:
    assert sniff(b"\xff\xd8\xff\xe0rest") == ("jpg", "image/jpeg")
    assert sniff(b"\x89PNG\r\n\x1a\nrest") == ("png", "image/png")
    assert sniff(b"RIFF1234WEBPVP8 ") == ("webp", "image/webp")
    assert sniff(b"GIF89a")[1] == "application/octet-stream"


def test_polygon_helpers() -> None:
    assert _norm_polygon([(-5, 3), (2000, 9.123)], 100, 50) == [[0.0, 3.0], [100.0, 9.12]]
    assert _area([[0, 0], [10, 0], [10, 5], [0, 5]]) == 50


def _scale(f: float, conf: Confidence, method=ScaleMethod.door, needs=False) -> ScaleResult:  # noqa: ANN001
    return ScaleResult(
        ft_per_px=f, method=method, confidence=conf, explanation="", needs_measurement=needs
    )


def test_keep_confirmation_rules() -> None:
    med = _scale(0.1, Confidence.medium)
    high = _scale(0.1, Confidence.high, ScaleMethod.user_measurement)
    assert _keep_confirmation(None, high, False)
    assert _keep_confirmation(med, _scale(0.1005, Confidence.medium), True)
    assert not _keep_confirmation(med, _scale(0.12, Confidence.medium), True)
    assert not _keep_confirmation(med, _scale(0.1, Confidence.medium), False)
    assert not _keep_confirmation(med, _scale(0.1, Confidence.low, ScaleMethod.floors, True), True)


def test_floors_from_answer() -> None:
    assert floors_from_answer(None) is None
    answers = SimpleNamespace(floors=ChoiceResult(choice="4 or more"))
    assert floors_from_answer(answers) == 4  # type: ignore[arg-type]
    assert floors_from_answer(SimpleNamespace(floors=ChoiceResult(choice="?"))) is None  # type: ignore[arg-type]
    assert WholePhotoAnswers  # contract import stays valid


def test_queue_dsn_from_database_url() -> None:
    s = Settings(database_url="postgresql+asyncpg://u:p@h:1/db")
    assert s.queue_dsn == "postgresql://u:p@h:1/db"
    assert Settings(database_url="postgres://u@h/db").queue_dsn == "postgresql://u@h/db"
