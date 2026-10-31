"""Daily per-person limits on the steps that call paid AI (photo analysis, new looks)."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Design, ImageRow, Project, Render, User
from app.services.errors import ApiException


def _start_of_day() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _limit_reached(what: str, limit: int) -> ApiException:
    return ApiException(
        429,
        "daily_limit",
        f"You've reached today's limit of {limit} {what}. Please try again tomorrow.",
    )


async def check_photo_limit(session: AsyncSession, user: User) -> None:
    limit = get_settings().daily_photo_limit
    if limit <= 0:
        return
    used = await session.scalar(
        select(func.count(ImageRow.id))
        .join(Project, Project.id == ImageRow.project_id)
        .where(
            Project.owner_id == user.id,
            ImageRow.kind == "original",
            ImageRow.created_at >= _start_of_day(),
        )
    )
    if (used or 0) >= limit:
        raise _limit_reached("photo checks", limit)


async def check_new_look_limit(session: AsyncSession, user: User) -> None:
    limit = get_settings().daily_new_look_limit
    if limit <= 0:
        return
    used = await session.scalar(
        select(func.count(Render.id))
        .join(Design, Design.id == Render.design_id)
        .join(Project, Project.id == Design.project_id)
        .where(Project.owner_id == user.id, Render.created_at >= _start_of_day())
    )
    if (used or 0) >= limit:
        raise _limit_reached("new looks", limit)
