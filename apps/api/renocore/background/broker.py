"""The Procrastinate app (Postgres-backed queue) and the retry policy for every job."""

import procrastinate
from procrastinate.jobs import Job
from procrastinate.retry import BaseRetryStrategy, RetryDecision

from renocore.settings import get_settings

TASK_NAMES = {
    "analyze_photo": "analyze_photo",
    "material_advice": "material_advice",
    "render": "render",
    "report": "report",
}


def is_retryable(exc: BaseException) -> bool:
    """Requests a provider rejected as invalid (4xx other than 429) will fail the same way again."""
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "code", None)
    if isinstance(status, int) and 400 <= status < 500 and status not in (408, 429):
        return False
    return True


class SettingsRetry(BaseRetryStrategy):
    """Whole-job retry with exponential backoff; limits read from settings at run time."""

    def get_retry_decision(self, *, exception: BaseException, job: Job) -> RetryDecision | None:
        settings = get_settings()
        if job.attempts + 1 >= settings.job_max_attempts or not is_retryable(exception):
            return None
        return RetryDecision(
            retry_in={"seconds": settings.job_retry_base_seconds * 2**job.attempts}
        )


def is_final_attempt(job: Job, exception: BaseException | None = None) -> bool:
    if exception is not None and not is_retryable(exception):
        return True
    return job.attempts + 1 >= get_settings().job_max_attempts


queue_app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=get_settings().queue_dsn),
    import_paths=["renocore.background.handlers"],
)
