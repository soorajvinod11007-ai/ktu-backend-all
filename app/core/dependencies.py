"""Cross-cutting FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from app.core.config import get_settings
from app.core.exceptions import TooManyRequestsError
from app.core.rate_limit import get_rate_limiter


def _client_ip(request: Request) -> str:
    # If you sit behind a trusted proxy, read X-Forwarded-For here.
    # For now, trust the socket peer.
    return request.client.host if request.client else "unknown"


def rate_limit_login(request: Request) -> None:
    """Apply the per-IP login rate limit. Raises 429 on overflow."""
    settings = get_settings()
    limiter = get_rate_limiter()
    key = f"login:{_client_ip(request)}"
    allowed, retry_after = limiter.hit(
        key,
        max_hits=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
        window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    )
    if not allowed:
        raise TooManyRequestsError(
            "Too many login attempts. Please try again later.",
            retry_after=retry_after,
        )


__all__ = ["rate_limit_login"]