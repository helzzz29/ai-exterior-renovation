"""Thin google-genai wrapper: Tenacity retries, timeouts, concurrency cap and tracing.

The Gemini key may be on the free tier with strict rate limits, so retries happen only for
429 / 500 / 503 / 504 and timeouts, with exponential backoff + jitter, honouring the server's
RetryInfo delay on 429. The SDK's own retries are left off (its default) so they don't stack.
"""

import asyncio
import random
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from google import genai
from google.genai import errors, types
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt

from app.ai.tracing import Tracer
from app.domain.ai import AICallRecord

log = structlog.get_logger(__name__)

RETRY_STATUS = frozenset({429, 500, 503, 504})
MAX_ATTEMPTS = 5
BACKOFF_INITIAL_S = 2.0
BACKOFF_MAX_S = 60.0
MAX_RETRY_DELAY_S = 90.0
CALL_TIMEOUT_S = 180.0

try:  # httpx2 is the transport of typesafe-sdk and may also back google-genai
    import httpx2

    _TIMEOUT_EXC: tuple[type[BaseException], ...] = (
        TimeoutError,
        httpx.TimeoutException,
        httpx2.TimeoutException,
    )
except ImportError:  # pragma: no cover
    _TIMEOUT_EXC = (TimeoutError, httpx.TimeoutException)


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, errors.APIError):
        return exc.code in RETRY_STATUS
    return isinstance(exc, _TIMEOUT_EXC)


_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s*$")


def retry_delay_seconds(exc: BaseException) -> float | None:
    """Server-suggested delay from a 429's google.rpc.RetryInfo detail, if present."""
    if not isinstance(exc, errors.APIError) or exc.code != 429:
        return None
    details = exc.details
    if isinstance(details, dict):
        details = details.get("error", details).get("details", [])
    if not isinstance(details, list):
        return None
    for item in details:
        if isinstance(item, dict) and str(item.get("@type", "")).endswith("RetryInfo"):
            match = _DURATION.match(str(item.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    return None


def backoff_wait(state: RetryCallState) -> float:
    exc = state.outcome.exception() if state.outcome is not None else None
    suggested = retry_delay_seconds(exc) if exc is not None else None
    if suggested is not None:
        return min(suggested, MAX_RETRY_DELAY_S) + random.uniform(0, 1)  # noqa: S311
    exp = min(BACKOFF_MAX_S, BACKOFF_INITIAL_S * 2 ** (state.attempt_number - 1))
    return exp / 2 + random.uniform(0, exp / 2)  # noqa: S311


@dataclass
class GeminiCall:
    response: types.GenerateContentResponse
    attempts: int
    latency_ms: int


def usage_of(response: Any) -> tuple[int | None, int | None]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None, None
    out = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
    return usage.prompt_token_count, out or None


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        max_concurrency: int,
        tracer: Tracer,
        client: Any | None = None,
        wait: Any = backoff_wait,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._sem = asyncio.Semaphore(max_concurrency)
        self._tracer = tracer
        self._wait = wait

    @property
    def client(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("GEMINI_API_KEY is not set; cannot call Gemini.")
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=int(CALL_TIMEOUT_S * 1000)),
            )
        return self._client

    async def generate(
        self,
        *,
        step: str,
        model: str,
        contents: list[Any],
        config: types.GenerateContentConfig,
        prompt_version: str | None,
        input_hash: str,
    ) -> GeminiCall:
        """One logical call (with retries). Records success or final failure."""
        attempts = 0
        started = time.perf_counter()

        async def once() -> types.GenerateContentResponse:
            nonlocal attempts
            attempts += 1
            async with self._sem:
                return await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=model, contents=contents, config=config
                    ),
                    timeout=CALL_TIMEOUT_S,
                )

        retrying = AsyncRetrying(
            stop=stop_after_attempt(MAX_ATTEMPTS),
            wait=self._wait,
            retry=retry_if_exception(is_retryable),
            reraise=True,
        )
        try:
            response = await retrying(once)
        except Exception as exc:
            await self._tracer.record(
                AICallRecord(
                    step=step,  # type: ignore[arg-type]
                    provider="gemini",
                    model=model,
                    prompt_version=prompt_version,
                    input_hash=input_hash,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    attempts=max(attempts, 1),
                    error=f"{type(exc).__name__}: {exc}"[:500],
                )
            )
            raise
        return GeminiCall(
            response=response,
            attempts=attempts,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def record(
        self,
        call: GeminiCall,
        *,
        step: str,
        model: str,
        prompt_version: str | None,
        input_hash: str,
        output: dict | None,
        error: str | None = None,
    ) -> None:
        input_tokens, output_tokens = usage_of(call.response)
        await self._tracer.record(
            AICallRecord(
                step=step,  # type: ignore[arg-type]
                provider="gemini",
                model=model,
                prompt_version=prompt_version,
                input_hash=input_hash,
                output=output,
                latency_ms=call.latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=None,  # free tier; no reliable price to estimate
                attempts=call.attempts,
                request_id=getattr(call.response, "response_id", None),
                error=error,
            )
        )

    async def record_cached(
        self, *, step: str, model: str, prompt_version: str | None, input_hash: str, output: dict
    ) -> None:
        await self._tracer.record(
            AICallRecord(
                step=step,  # type: ignore[arg-type]
                provider="gemini",
                model=model,
                prompt_version=prompt_version,
                input_hash=input_hash,
                output=output,
                latency_ms=0,
                cost_usd=0.0,
                attempts=0,
                cached=True,
            )
        )
