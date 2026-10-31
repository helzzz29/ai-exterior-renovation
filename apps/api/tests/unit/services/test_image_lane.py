"""The shared image thread: one piece of full-size image work at a time, context kept."""

import asyncio
import contextvars
import threading
import time

import pytest

from app.services.image_lane import run_image_work


async def test_image_work_never_overlaps() -> None:
    lock = threading.Lock()
    active = 0
    most = 0

    def heavy(n: int) -> int:
        nonlocal active, most
        with lock:
            active += 1
            most = max(most, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return n * 2

    results = await asyncio.gather(*(run_image_work(heavy, n) for n in range(4)))
    assert results == [0, 2, 4, 6]
    assert most == 1


async def test_image_work_keeps_context_and_kwargs() -> None:
    var: contextvars.ContextVar[str] = contextvars.ContextVar("job", default="none")
    var.set("job-1")

    def read(suffix: str = "") -> str:
        return var.get() + suffix

    assert await run_image_work(read, suffix="!") == "job-1!"


async def test_image_work_errors_reach_the_caller() -> None:
    def boom() -> None:
        raise ValueError("bad image")

    with pytest.raises(ValueError, match="bad image"):
        await run_image_work(boom)
