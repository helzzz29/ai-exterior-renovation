"""Enqueueing background work with idempotency, and the `job_runs` status we expose."""

from dataclasses import dataclass, field

import structlog
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_scope
from app.domain.api import JobOut
from app.jobs.queue import TASK_NAMES, queue_app
from app.models import JobRun, Project, new_id
from app.services.errors import ApiException

log = structlog.get_logger("jobs")

ACTIVE = ("queued", "running")

FIRST_STEP = {
    "analyze_photo": "Checking your photo",
    "material_advice": "Finding materials that suit your house",
    "render": "Creating your new look",
    "report": "Preparing your report",
}

FAILURE_MESSAGE = {
    "analyze_photo": "We couldn't finish checking your photo. Please try uploading it again.",
    "material_advice": "We couldn't prepare material suggestions. You can still choose materials.",
    "render": "We couldn't create your new look this time. Please try again.",
    "report": "We couldn't create your report. Please try again.",
    "relabel_regions": "We couldn't update the parts of your house. Please try again.",
}


def job_out(run: JobRun) -> JobOut:
    return JobOut(
        id=run.id,
        kind=run.kind,  # type: ignore[arg-type]
        status=run.status,  # type: ignore[arg-type]
        step=run.step,
        error=run.error,
    )


async def lock_project(session: AsyncSession, project_id: str) -> Project:
    """Row lock that serialises concurrent state changes (e.g. double-clicks) on a project."""
    project = await session.get(Project, project_id, with_for_update=True, populate_existing=True)
    assert project is not None
    return project


async def find_active(session: AsyncSession, idem_key: str) -> JobRun | None:
    return await session.scalar(
        select(JobRun)
        .where(JobRun.idem_key == idem_key, JobRun.status.in_(ACTIVE))
        .order_by(JobRun.created_at.desc())
        .limit(1)
    )


async def enqueue(
    session: AsyncSession,
    *,
    project_id: str,
    kind: str,
    idem_key: str,
    payload: dict | None = None,
    design_id: str | None = None,
    run_id: str | None = None,
) -> tuple[JobRun, bool]:
    """Create a job run and defer it. Returns (run, created). The same idem_key while a run
    is still queued/running returns the existing run (double submit -> one job).

    The caller should hold the project row lock (`lock_project`) so concurrent requests
    serialise; this function commits the session.
    """
    existing = await find_active(session, idem_key)
    if existing is not None:
        await session.commit()
        return existing, False
    run = JobRun(
        id=run_id or new_id(),
        project_id=project_id,
        design_id=design_id,
        kind=kind,
        status="queued",
        step=FIRST_STEP.get(kind),
        idem_key=idem_key,
        payload=payload or {},
    )
    session.add(run)
    await session.commit()
    try:
        queue_id = await queue_app.configure_task(
            name=TASK_NAMES[kind], queueing_lock=idem_key
        ).defer_async(job_run_id=run.id)
    except AlreadyEnqueued:
        # another process deferred the same work first; point at its run
        await session.delete(run)
        await session.commit()
        other = await session.scalar(
            select(JobRun).where(JobRun.idem_key == idem_key).order_by(JobRun.created_at.desc())
        )
        if other is None:  # pragma: no cover - defensive
            raise ApiException(503, "busy", "We're busy right now. Please try again.") from None
        return other, False
    except Exception as exc:
        log.exception("defer_failed", kind=kind)
        run.status = "failed"
        run.error = FAILURE_MESSAGE.get(kind)
        await session.commit()
        raise ApiException(
            503, "queue_unavailable", "We couldn't start this step. Please try again shortly."
        ) from exc
    run.queue_job_id = queue_id
    await session.commit()
    log.info("job_enqueued", job_id=run.id, kind=kind, project_id=project_id)
    return run, True


async def latest_active(session: AsyncSession, project_id: str) -> JobRun | None:
    return await session.scalar(
        select(JobRun)
        .where(JobRun.project_id == project_id, JobRun.status.in_(ACTIVE))
        .order_by(JobRun.created_at.desc())
        .limit(1)
    )


async def has_active(session: AsyncSession, project_id: str, kind: str) -> bool:
    found = await session.scalar(
        select(JobRun.id)
        .where(JobRun.project_id == project_id, JobRun.kind == kind, JobRun.status.in_(ACTIVE))
        .limit(1)
    )
    return found is not None


@dataclass
class JobCtx:
    """What a job handler gets: ids, payload, and a way to report progress."""

    run_id: str
    kind: str
    project_id: str
    design_id: str | None
    payload: dict = field(default_factory=dict)

    async def set_step(self, step: str) -> None:
        async with session_scope() as session:
            run = await session.get(JobRun, self.run_id)
            if run is not None:
                run.step = step
                await session.commit()
        log.info("job_step", step=step)
