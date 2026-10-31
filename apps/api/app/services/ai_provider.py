"""AI provider wiring: one factory (app.ai.get_provider) plus the ai_calls recorder."""

import structlog

from app import ai
from app.config import get_settings
from app.db import session_scope
from app.domain.ai import AICallRecord, AIProvider
from app.models import AICall

log = structlog.get_logger("ai")


class DbAICallRecorder:
    """Persists every model call to `ai_calls` in its own transaction (survives job failure)."""

    def __init__(self, project_id: str | None, job_id: str | None = None) -> None:
        self.project_id = project_id
        self.job_id = job_id

    async def record(self, call: AICallRecord) -> None:
        data = call.model_dump(exclude={"created_at"})
        row = AICall(project_id=self.project_id, job_id=self.job_id, **data)
        if call.created_at is not None:
            row.created_at = call.created_at
        try:
            async with session_scope() as session:
                session.add(row)
                await session.commit()
        except Exception:  # tracing must never break the pipeline
            log.exception("ai_call_record_failed", step=call.step)
            return
        log.info(
            "ai_call",
            step=call.step,
            provider=call.provider,
            model=call.model,
            latency_ms=call.latency_ms,
            attempts=call.attempts,
            cached=call.cached,
            error=call.error,
        )


def provider_for(project_id: str | None, job_id: str | None = None) -> AIProvider:
    """The single place the provider is created. Tests override `app.ai.get_provider`."""
    return ai.get_provider(get_settings(), DbAICallRecorder(project_id, job_id))
