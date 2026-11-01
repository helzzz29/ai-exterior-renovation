"""One background thread for full-size image work (decode, encode, resize, PDF).

The server has 512 MB of memory. Running this work on one shared thread means two jobs or
requests never hold full-size working copies at the same moment; under load the second one
waits a moment instead. Use it instead of `asyncio.to_thread` for anything that handles a
whole photo.
"""

import asyncio
import contextvars
import functools
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image-lane")


async def run_image_work[**P, T](fn: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> T:
    """Like `asyncio.to_thread` (log context included), but on the shared image thread."""
    loop = asyncio.get_running_loop()
    call = functools.partial(contextvars.copy_context().run, fn, *args, **kwargs)
    return await loop.run_in_executor(_EXECUTOR, call)
