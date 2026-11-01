"""Email + password auth: argon2 hashes, JWT in an httpOnly `session` cookie."""

from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from renocore.database import get_session
from renocore.operations.failures import ApiException
from renocore.settings import Settings, get_settings
from renocore.tables import User

COOKIE_NAME = "session"
_ALGO = "HS256"
_hasher = PasswordHasher()
# hashed once so unknown-email logins take as long as wrong-password logins
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_token(user_id: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(hours=settings.jwt_ttl_hours)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def decode_token(token: str, settings: Settings) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGO])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None


def set_session_cookie(response: Response, user_id: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_token(user_id, settings),
        max_age=settings.jwt_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.env == "prod",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=settings.env == "prod"
    )


def not_signed_in() -> ApiException:
    return ApiException(401, "not_signed_in", "Please sign in to continue.")


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    # read the cookie from the request (not a Cookie() parameter) to keep the OpenAPI contract
    token = request.cookies.get(COOKIE_NAME)
    user_id = decode_token(token, get_settings()) if token else None
    if user_id is None:
        raise not_signed_in()
    user = await session.get(User, user_id)
    if user is None:
        raise not_signed_in()
    return user


async def register_user(session: AsyncSession, email: str, password: str) -> User:
    if not get_settings().signup_open:
        raise ApiException(
            403,
            "signup_closed",
            "New accounts can't be created here. Please sign in with the account you were given.",
        )
    email = email.strip().lower()
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ApiException(
            409, "email_taken", "An account with this email already exists. Please sign in."
        )
    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    await session.commit()
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        verify_password(_DUMMY_HASH, password)
        ok = False
    else:
        ok = verify_password(user.password_hash, password)
    if not ok or user is None:
        raise ApiException(
            401, "invalid_credentials", "That email and password don't match. Please try again."
        )
    return user


async def ensure_seed_users(session: AsyncSession, users: dict[str, str]) -> int:
    """Create or update the invited accounts ({email: argon2 hash}); returns how many changed."""
    changed = 0
    for raw_email, password_hash in users.items():
        if not password_hash.startswith("$argon2"):
            raise ValueError(f"seed user {raw_email!r}: expected an argon2 hash, not a password")
        email = raw_email.strip().lower()
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            session.add(User(email=email, password_hash=password_hash))
            changed += 1
        elif user.password_hash != password_hash:
            user.password_hash = password_hash
            changed += 1
    await session.commit()
    return changed
