"""Thin TypeSafe Jev wrapper: client setup, semaphore, cache, attempt counting and tracing.

Answers are converted to plain JSON dicts (`answer.model_dump(mode="json")`) so they can be cached,
recorded and parsed the same way whether they came from the API or from the cache.
"""

import asyncio
import contextvars
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from typesafe_sdk import AsyncTypeSafeClient, Image, RetryPolicy

from renocore.schemas.vision_io import AICallRecord
from renocore.vision.audit import Tracer, jev_cost
from renocore.vision.memo import FileCache, cache_key, sha256_bytes

IMAGES_HEADER = {"TypeSafe-Danger-Zone-Images": "true"}
JEV_RETRY = RetryPolicy(max_retries=4, backoff_initial=0.5, backoff_max=8, timeout=60)

_attempts: contextvars.ContextVar[list[int] | None] = contextvars.ContextVar(
    "jev_attempts", default=None
)


async def _count_attempt(_request: Any) -> None:
    counter = _attempts.get()
    if counter is not None:
        counter[0] += 1


def jev_image(data: bytes) -> Image:
    return Image(data)


def describe(content: Any) -> Any:
    """JSON-safe, deterministic description of Jev content (images become their sha256).

    Used for cache keys and request snapshot tests.
    """
    if isinstance(content, Image):
        return {"image": sha256_bytes(bytes(content.data))}  # type: ignore[arg-type]
    if isinstance(content, BaseModel):
        return {
            key: describe(getattr(content, key))
            for key in ("type", "instructions", "criteria")
            if getattr(content, key, None) is not None
        }
    if isinstance(content, Mapping):
        return {str(k): describe(v) for k, v in content.items()}
    if isinstance(content, list | tuple):
        return [describe(v) for v in content]
    return content


def image_hashes(content: Any) -> list[str]:
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, Image):
            found.append(sha256_bytes(bytes(value.data)))  # type: ignore[arg-type]
        elif isinstance(value, BaseModel):
            walk(getattr(value, "instructions", None))
            walk(getattr(value, "criteria", None))
        elif isinstance(value, Mapping):
            for v in value.values():
                walk(v)
        elif isinstance(value, list | tuple):
            for v in value:
                walk(v)

    walk(content)
    return found


@dataclass
class JevResult:
    answers: dict[str, dict[str, Any]]
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str | None = None
    attempts: int = 1
    cached: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def _min_confidence(answers: dict[str, dict[str, Any]]) -> float | None:
    values = [a["confidence"] for a in answers.values() if a.get("confidence") is not None]
    return min(values) if values else None


class JevClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_concurrency: int,
        tracer: Tracer,
        cache: FileCache | None = None,
        client: AsyncTypeSafeClient | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._client = client
        self._sem = asyncio.Semaphore(max_concurrency)
        self._tracer = tracer
        self._cache = cache

    @property
    def client(self) -> AsyncTypeSafeClient:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("JEV_API_KEY is not set; cannot call TypeSafe Jev.")
            self._client = AsyncTypeSafeClient(
                api_key=self._api_key, model=self.model, headers=IMAGES_HEADER, retry=JEV_RETRY
            )
        self._install_hook(self._client)
        return self._client

    @staticmethod
    def _install_hook(client: AsyncTypeSafeClient) -> None:
        http = getattr(client, "_http_client", None)
        hooks = getattr(http, "event_hooks", None)
        if hooks is None:
            return
        if _count_attempt not in hooks.get("request", []):
            hooks["request"].append(_count_attempt)

    async def ask(
        self,
        step: str,
        state: Any,
        questions: Mapping[str, Any],
        prompt_version: str | None = None,
    ) -> JevResult:
        hashes = image_hashes(state) + image_hashes(questions)
        payload = {"state": describe(state), "questions": describe(questions)}
        key = cache_key(step, self.model, prompt_version, hashes, payload)
        input_hash = key
        if self._cache is not None:
            hit = self._cache.get_json(key)
            if hit is not None:
                result = JevResult(answers=hit["answers"], attempts=0, cached=True)
                await self._tracer.record(
                    AICallRecord(
                        step=step,  # type: ignore[arg-type]
                        provider="jev",
                        model=self.model,
                        prompt_version=prompt_version,
                        input_hash=input_hash,
                        output=hit["answers"],
                        confidence=_min_confidence(hit["answers"]),
                        latency_ms=0,
                        cost_usd=0.0,
                        attempts=0,
                        cached=True,
                    )
                )
                return result

        counter = [0]
        token = _attempts.set(counter)
        started = time.perf_counter()
        try:
            async with self._sem:
                response = await self.client.system_one(state=state, questions=questions)
        except Exception as exc:
            await self._tracer.record(
                AICallRecord(
                    step=step,  # type: ignore[arg-type]
                    provider="jev",
                    model=self.model,
                    prompt_version=prompt_version,
                    input_hash=input_hash,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    attempts=max(counter[0], 1),
                    error=f"{type(exc).__name__}: {exc}"[:500],
                )
            )
            raise
        finally:
            _attempts.reset(token)

        answers = {name: ans.model_dump(mode="json") for name, ans in response.answers.items()}
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        try:
            request_id = response.request_id
        except Exception:
            request_id = None
        result = JevResult(
            answers=answers,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            request_id=request_id,
            attempts=max(counter[0], 1),
        )
        if self._cache is not None:
            self._cache.put_json(key, {"answers": answers})
        await self._tracer.record(
            AICallRecord(
                step=step,  # type: ignore[arg-type]
                provider="jev",
                model=self.model,
                prompt_version=prompt_version,
                input_hash=input_hash,
                output=answers,
                confidence=_min_confidence(answers),
                latency_ms=int((time.perf_counter() - started) * 1000),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=jev_cost(input_tokens),
                attempts=result.attempts,
                request_id=request_id,
            )
        )
        return result

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
