"""Procrastinate tasks. Each one updates our `job_runs` row (status + plain-language step)."""

from collections.abc import Awaitable, Callable

import structlog
from procrastinate import JobContext

from renocore.background.broker import SettingsRetry, is_final_attempt, queue_app
from renocore.database import session_scope
from renocore.operations import detection as analysis
from renocore.operations import exports as reports
from renocore.operations import makeovers as designs
from renocore.operations.job_runner import FAILURE_MESSAGE, FIRST_STEP, JobCtx
from renocore.operations.telemetry import memory_mb
from renocore.tables import JobRun

log = structlog.get_logger("jobs")

Handler = Callable[[JobCtx], Awaitable[None]]


async def execute(
    context: JobContext,
    job_run_id: str,
    handler: Handler,
    on_final_failure: Handler | None = None,
) -> None:
    structlog.contextvars.bind_contextvars(job_id=job_run_id, queue_job_id=context.job.id)
    kind: str | None = None
    try:
        async with session_scope() as session:
            run = await session.get(JobRun, job_run_id)
            if run is None or run.status == "done":
                log.info("job_skipped", reason="missing" if run is None else "already_done")
                return
            run.status = "running"
            run.attempts = context.job.attempts + 1
            run.error = None
            if run.step is None:
                run.step = FIRST_STEP.get(run.kind)
            await session.commit()
            ctx = JobCtx(
                run_id=run.id,
                kind=run.kind,
                project_id=run.project_id,
                design_id=run.design_id,
                payload=dict(run.payload or {}),
            )
        log.info("job_started", kind=ctx.kind, attempt=context.job.attempts + 1)
        kind = ctx.kind
        log_memory(kind, "start")
        try:
            await handler(ctx)
        except Exception as exc:
            final = is_final_attempt(context.job, exc)
            log.exception("job_failed", kind=ctx.kind, final=final)
            async with session_scope() as session:
                run = await session.get(JobRun, job_run_id)
                if run is not None:
                    if final:
                        run.status = "failed"
                        run.error = FAILURE_MESSAGE.get(run.kind, "Something went wrong.")
                    else:
                        run.status = "queued"
                        run.step = "Trying again"
                    await session.commit()
            if final and on_final_failure is not None:
                await on_final_failure(ctx)
            raise
        async with session_scope() as session:
            run = await session.get(JobRun, job_run_id)
            if run is not None:
                run.status = "done"
                run.step = None
                await session.commit()
        log.info("job_done", kind=ctx.kind)
    finally:
        if kind is not None:
            log_memory(kind, "end")
        structlog.contextvars.unbind_contextvars("job_id", "queue_job_id")


def log_memory(kind: str, at: str) -> None:
    """`job_memory` line with the process's current and peak memory (Linux only)."""
    current, peak = memory_mb()
    if current is not None:
        log.info("job_memory", kind=kind, at=at, rss_mb=current, peak_mb=peak)


@queue_app.task(name="analyze_photo", pass_context=True, retry=SettingsRetry())
async def analyze_photo(context: JobContext, job_run_id: str) -> None:
    await execute(context, job_run_id, analysis.run_analysis, analysis.analysis_failed)


@queue_app.task(name="material_advice", pass_context=True, retry=SettingsRetry())
async def material_advice(context: JobContext, job_run_id: str) -> None:
    await execute(context, job_run_id, analysis.run_material_advice)


@queue_app.task(name="render", pass_context=True, retry=SettingsRetry())
async def render(context: JobContext, job_run_id: str) -> None:
    await execute(context, job_run_id, designs.run_render, designs.render_failed)


@queue_app.task(name="report", pass_context=True, retry=SettingsRetry())
async def report(context: JobContext, job_run_id: str) -> None:
    await execute(context, job_run_id, reports.run_report)
