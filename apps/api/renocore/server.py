import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from renocore.endpoints import router
from renocore.operations.failures import ApiException, api_exception_handler
from renocore.operations.telemetry import RequestIdMiddleware, configure_logging
from renocore.settings import get_settings

log = structlog.get_logger("renocore")

# a job whose worker stopped sending heartbeats (e.g. the server slept mid-job) is retried
STALLED_AFTER_SECONDS = 60
STALLED_SWEEP_SECONDS = 60


DEFAULT_SEED_USERS: dict[str, str] = {
    "admin@example.com": "$argon2id$v=19$m=65536,t=3,p=4$eyafpJikw5ok9z9gco2s3Q$vLRLiq5zRH+3fF/Z5ma4qBStkNdqFV0tlym3Ze+gUWE",
    "user@example.com": "$argon2id$v=19$m=65536,t=3,p=4$GH+AS3rXcYW45+u3mSaWag$K9z4xR2JjqWjaX8Z+E8uySZJAeg3jRRlcbIqrwZwp8Q",
    "user1@example.com": "$argon2id$v=19$m=65536,t=3,p=4$jmh1T60g8K0s1afkbrS1tA$BJOzjMN9oschHUUGrATd1PCYxZfhuNiorF0ySOIqVqo",
    "user2@example.com": "$argon2id$v=19$m=65536,t=3,p=4$kpYJYXoazx8UmNcmeRNWoA$KBAdQR6OIkote1KKDfdtQUM+ZAODioLn/PDb2FfghcQ",
}


async def _seed_users() -> None:
    from renocore.database import session_scope
    from renocore.identity import ensure_seed_users

    users = {**DEFAULT_SEED_USERS, **get_settings().seed_users}
    async with session_scope() as session:
        changed = await ensure_seed_users(session, users)
    log.info("seed_users", accounts=len(users), changed=changed)


async def _retry_stalled_jobs() -> None:
    from renocore.background.broker import queue_app

    while True:
        with suppress(Exception):  # a missed sweep is retried on the next one
            stalled = await queue_app.job_manager.get_stalled_jobs(
                seconds_since_heartbeat=STALLED_AFTER_SECONDS
            )
            for job in stalled:
                log.warning("job_stalled_retry", queue_job_id=job.id, task=job.task_name)
                await queue_app.job_manager.retry_job(job)
        await asyncio.sleep(STALLED_SWEEP_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    from renocore.background.broker import queue_app
    from renocore.database import dispose_engine

    settings = get_settings()
    await _seed_users()
    async with queue_app.open_async():
        background: list[asyncio.Task] = []
        if settings.run_worker:  # production: one process runs the API and the jobs
            background.append(
                asyncio.create_task(
                    queue_app.run_worker_async(
                        concurrency=settings.worker_concurrency, install_signal_handlers=False
                    )
                )
            )
            background.append(asyncio.create_task(_retry_stalled_jobs()))
        # otherwise the API only defers jobs; the worker process runs them
        try:
            yield
        finally:
            for task in background:
                task.cancel()
            for task in background:
                with suppress(BaseException):
                    await task
    await dispose_engine()


def mount_website(app: FastAPI, dist: Path) -> None:
    """Serve the built React app; unknown non-API paths get index.html (client-side routes)."""
    root = dist.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    async def website(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise ApiException(404, "not_found", "We couldn't find that.")
        file = (root / path).resolve()
        if path and root in file.parents and file.is_file():
            # hashed bundles never change; everything else is re-checked
            immutable = path.startswith("assets/")
            cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
            return FileResponse(file, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(title="Renovation Planner API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(ApiException, api_exception_handler)
    app.include_router(router)
    # material swatch images (static, public); not part of the OpenAPI schema
    app.mount(
        "/api/swatches",
        StaticFiles(directory=settings.seed_dir / "swatches", check_dir=False),
        name="swatches",
    )

    @app.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    if settings.web_dist is not None:
        mount_website(app, settings.web_dist)
    return app


app = create_app()


if __name__ == "__main__":  # `python -m renocore.server` (selector loop works on Windows too)
    import uvicorn

    if sys.platform == "win32":  # psycopg's async mode needs a selector event loop
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    settings = get_settings()
    uvicorn.run(
        "renocore.server:app",
        host=settings.host,
        port=settings.port,
        loop="none",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
