"""Worker entry point: `uv run python -m app.jobs.worker` (run as many processes as needed)."""

import asyncio
import sys

from app.config import get_settings
from app.services.observability import configure_logging


async def main() -> None:
    from app.jobs import tasks  # noqa: F401  (registers the tasks)
    from app.jobs.queue import queue_app

    settings = get_settings()
    async with queue_app.open_async():
        await queue_app.run_worker_async(concurrency=settings.worker_concurrency)


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    if sys.platform == "win32":  # psycopg's async mode needs a selector loop on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())


if __name__ == "__main__":
    run()
