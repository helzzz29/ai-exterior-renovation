"""structlog JSON logging with request / job correlation ids."""

import logging
import os
import sys
import time
import uuid
from pathlib import Path

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_configured = False


def configure_logging(level: str = "INFO", json: bool = True) -> None:
    global _configured
    if _configured:
        return
    _configured = True
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    renderer = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger("api")

_STATM = Path("/proc/self/statm")


def memory_mb() -> tuple[float | None, float | None]:
    """(current, peak) resident memory of this process in MB, from /proc and getrusage.

    Linux only (production); elsewhere (None, None). Never raises.
    """
    try:
        import resource

        pages = int(_STATM.read_text().split()[1])
        current = pages * os.sysconf("SC_PAGE_SIZE") / 2**20
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KB on Linux
        return round(current, 1), round(peak, 1)
    except Exception:
        return None, None


class RequestIdMiddleware:
    """Binds a request id (incoming X-Request-ID or a new one) to every log line."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")[:64]
        request_id = incoming or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        status_holder: dict[str, int] = {}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                message.setdefault("headers", [])
                message["headers"] = [
                    *message["headers"],
                    (b"x-request-id", request_id.encode("latin-1")),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            log.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_holder.get("status"),
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
            structlog.contextvars.clear_contextvars()
