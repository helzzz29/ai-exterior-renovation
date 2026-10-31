"""JevClient: retries through the real SDK on a mock transport, cache, tracing."""

import json

import httpx2
import pytest
from typesafe_sdk import AsyncTypeSafeClient, Image, Noul, RetryPolicy

from app.ai.cache import FileCache
from app.ai.jev_client import IMAGES_HEADER, JEV_RETRY, JevClient, describe, image_hashes
from app.ai.tracing import Tracer
from tests.unit.ai.conftest import FakeJevSDK, make_jev

OK_BODY = {
    "model": "jev-latest",
    "usage": {"input_tokens": 2000, "output_tokens": 4},
    "answers": {"q": {"type": "noul", "noul": 0.75}},
}


def sdk_with(responses: list[httpx2.Response], seen: list[httpx2.Request]) -> AsyncTypeSafeClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return responses.pop(0)

    return AsyncTypeSafeClient(
        api_key="test-key",
        model="jev-latest",
        headers=IMAGES_HEADER,
        retry=RetryPolicy(max_retries=4, backoff_initial=0, backoff_max=0),
        transport=httpx2.MockTransport(handler),
    )


async def test_429_then_success_retries_once(recorder):
    seen: list[httpx2.Request] = []
    sdk = sdk_with(
        [
            httpx2.Response(429, json={"detail": "slow down"}),
            httpx2.Response(200, json=OK_BODY, headers={"x-typesafe-request-id": "req-42"}),
        ],
        seen,
    )
    jev = JevClient("test-key", "jev-latest", 2, Tracer(recorder), client=sdk)
    result = await jev.ask(
        "C1", ["photo:", Image(b"\xff\xd8\xff fake")], {"q": Noul(instructions="Is it?")}
    )
    assert len(seen) == 2
    assert seen[0].headers["TypeSafe-Danger-Zone-Images"] == "true"
    assert result.answers == {"q": {"type": "noul", "noul": 0.75}}
    assert result.attempts == 2
    assert result.request_id == "req-42"
    rec = recorder.calls[-1]
    assert rec.attempts == 2 and rec.request_id == "req-42" and rec.input_tokens == 2000
    assert rec.cost_usd == pytest.approx(2000 * 0.042 / 1e6)
    await jev.aclose()


async def test_non_retryable_error_is_recorded_and_raised(recorder):
    seen: list[httpx2.Request] = []
    sdk = sdk_with([httpx2.Response(400, json={"detail": "bad"})], seen)
    jev = JevClient("k", "jev-latest", 2, Tracer(recorder), client=sdk)
    with pytest.raises(Exception, match="400"):
        await jev.ask("C3", "state", {"q": Noul(instructions="x")})
    assert len(seen) == 1
    assert recorder.calls[0].error and recorder.calls[0].attempts == 1


async def test_cache_hit_avoids_second_call(tmp_path, recorder):
    sdk = FakeJevSDK()
    cache = FileCache(tmp_path)
    jev = make_jev(sdk, recorder, cache)
    questions = {"q": Noul(instructions="Is it?")}
    first = await jev.ask("C1", ["p", Image(b"abc")], questions, prompt_version="v1")
    again = await jev.ask("C1", ["p", Image(b"abc")], questions, prompt_version="v1")
    assert len(sdk.calls) == 1
    assert again.cached and again.answers == first.answers
    assert [c.cached for c in recorder.calls] == [False, True]
    assert recorder.calls[1].attempts == 0 and recorder.calls[1].cost_usd == 0.0
    # a different image or prompt version is a different key
    await jev.ask("C1", ["p", Image(b"abd")], questions, prompt_version="v1")
    await jev.ask("C1", ["p", Image(b"abc")], questions, prompt_version="v2")
    assert len(sdk.calls) == 3
    assert recorder.calls[0].input_hash == recorder.calls[1].input_hash


async def test_recorder_failure_does_not_break_call():
    class Broken:
        async def record(self, call):
            raise RuntimeError("db down")

    jev = make_jev(FakeJevSDK(), Broken())
    result = await jev.ask("C1", "s", {"q": Noul(instructions="x")})
    assert result.answers["q"]["noul"] == 0.9


def test_missing_key_is_clear_error():
    jev = JevClient("", "jev-latest", 1, Tracer())
    with pytest.raises(RuntimeError, match="JEV_API_KEY"):
        _ = jev.client


def test_real_client_configuration():
    jev = JevClient("abc", "jev-latest", 1, Tracer())
    client = jev.client
    assert client is jev.client  # built once
    assert JEV_RETRY.max_retries == 4 and JEV_RETRY.backoff_max == 8 and JEV_RETRY.timeout == 60
    assert client._config.default_model == "jev-latest"


def test_describe_and_hashes_are_deterministic():
    q = {"a": Noul(instructions=["look", Image(b"x")])}
    assert describe(q) == describe({"a": Noul(instructions=["look", Image(b"x")])})
    assert json.dumps(describe(q))  # JSON-safe
    assert len(image_hashes(q)) == 1
    assert image_hashes(("s", Image(b"y"), {"k": Image(b"z")})) and describe(("t",)) == ["t"]
