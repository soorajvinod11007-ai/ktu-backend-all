"""Request-scoped middleware: correlation IDs + safe request logging.

Hard rule: request bodies for /auth/* are never read, buffered, or logged.
They may contain credentials or tokens. The allowlist below is checked
before any body access happens.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger("app.request")

# Paths whose request bodies must NEVER be read or logged.
BODY_LOG_DENY_PREFIXES: tuple[str, ...] = (
    "/api/v1/auth/",
)


def _should_log_body(path: str) -> bool:
    return not any(path.startswith(prefix) for prefix in BODY_LOG_DENY_PREFIXES)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a stable X-Request-ID to every request/response, and emit a
    single structured log line per request. Auth bodies are skipped."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        response.headers["X-Request-ID"] = request_id

        # Do NOT touch request.body() here (or anywhere) unless
        # _should_log_body(request.url.path) is True.
        extra = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        }
        if _should_log_body(request.url.path):
            # Body logging not enabled here — add it here only if you need it,
            # and only behind this guard.
            pass
        logger.info("request", extra=extra)

        return response