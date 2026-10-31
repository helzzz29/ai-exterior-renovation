import pytest

from app.jobs.queue import is_retryable


class _Err(Exception):
    def __init__(self, **attrs: object) -> None:
        super().__init__("boom")
        for k, v in attrs.items():
            setattr(self, k, v)


@pytest.mark.parametrize(
    ("exc", "retryable"),
    [
        (_Err(status=400), False),  # TypeSafe-style .status
        (_Err(status=422), False),
        (_Err(code=403), False),  # google-genai-style .code
        (_Err(status=429), True),
        (_Err(status=408), True),
        (_Err(status=503), True),
        (_Err(code=500), True),
        (RuntimeError("no status"), True),
        (_Err(code="INVALID_ARGUMENT"), True),  # non-numeric codes are not treated as 4xx
    ],
)
def test_is_retryable(exc: BaseException, retryable: bool) -> None:
    assert is_retryable(exc) is retryable
