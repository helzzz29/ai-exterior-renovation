from types import SimpleNamespace

from renocore.background.broker import SettingsRetry, is_final_attempt
from renocore.settings import get_settings


def test_exponential_backoff_until_max_attempts(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "job_max_attempts", 3)
    monkeypatch.setattr(settings, "job_retry_base_seconds", 2.0)
    strategy = SettingsRetry()
    first = strategy.get_retry_decision(exception=RuntimeError(), job=SimpleNamespace(attempts=0))
    second = strategy.get_retry_decision(exception=RuntimeError(), job=SimpleNamespace(attempts=1))
    last = strategy.get_retry_decision(exception=RuntimeError(), job=SimpleNamespace(attempts=2))
    assert first is not None and second is not None and last is None
    assert second.retry_at > first.retry_at  # 2 s then 4 s
    assert not is_final_attempt(SimpleNamespace(attempts=1))  # type: ignore[arg-type]
    assert is_final_attempt(SimpleNamespace(attempts=2))  # type: ignore[arg-type]
