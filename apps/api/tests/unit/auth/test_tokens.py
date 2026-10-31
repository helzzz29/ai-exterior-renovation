from datetime import UTC, datetime, timedelta

import jwt

from app.auth import create_token, decode_token, hash_password, verify_password
from app.config import Settings


def test_password_hashing() -> None:
    h = hash_password("correct horse battery")
    assert h.startswith("$argon2")
    assert verify_password(h, "correct horse battery")
    assert not verify_password(h, "wrong")
    assert not verify_password("not-a-hash", "x")


def test_token_roundtrip_and_rejections() -> None:
    settings = Settings(jwt_secret="s" * 32)
    token = create_token("user-1", settings)
    assert decode_token(token, settings) == "user-1"
    assert decode_token(token, Settings(jwt_secret="t" * 32)) is None
    assert decode_token("garbage", settings) is None
    expired = jwt.encode(
        {"sub": "user-1", "exp": datetime.now(UTC) - timedelta(seconds=5)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    assert decode_token(expired, settings) is None
    no_sub = jwt.encode({"x": 1}, settings.jwt_secret, algorithm="HS256")
    assert decode_token(no_sub, settings) is None
