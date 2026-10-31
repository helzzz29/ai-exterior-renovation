"""Reports every AI call (cached or not) to the optional AICallRecorder."""

from datetime import UTC, datetime

import structlog

from app.domain.ai import AICallRecord, AICallRecorder

log = structlog.get_logger(__name__)

JEV_USD_PER_M_INPUT_TOKENS = 0.042  # output tokens are free


def jev_cost(input_tokens: int | None) -> float | None:
    if input_tokens is None:
        return None
    return round(input_tokens * JEV_USD_PER_M_INPUT_TOKENS / 1_000_000, 8)


class Tracer:
    def __init__(self, recorder: AICallRecorder | None = None) -> None:
        self.recorder = recorder

    async def record(self, call: AICallRecord) -> None:
        if call.created_at is None:
            call.created_at = datetime.now(UTC)
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
        if self.recorder is None:
            return
        try:
            await self.recorder.record(call)
        except Exception:  # tracing must never break an AI step
            log.exception("ai_call_record_failed", step=call.step)
