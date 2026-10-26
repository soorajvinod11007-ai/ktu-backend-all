"""Pluggable rate limiter.

The default backend is in-process memory, which is enough for a single-worker
dev setup. For multi-worker / multi-instance deployments, swap in a Redis
backend by pointing `RATE_LIMITER_BACKEND` (see `get_rate_limiter`).

Interface: `hit(key, max_hits, window_seconds) -> (allowed, retry_after)`.
`retry_after` is integer seconds until the next slot is available.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Protocol

from app.core.config import get_settings


class RateLimiter(Protocol):
    def hit(
        self,
        key: str,
        *,
        max_hits: int,
        window_seconds: int,
    ) -> tuple[bool, int]: ...


class InMemoryRateLimiter:
    """Sliding-window per key. Thread-safe; process-local."""

    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(
        self,
        key: str,
        *,
        max_hits: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._buckets[key]
            # Drop timestamps that fell out of the window.
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= max_hits:
                # Oldest hit leaves the window at bucket[0] + window_seconds.
                retry_after = int(bucket[0] + window_seconds - now) + 1
                return False, max(retry_after, 1)

            bucket.append(now)
            return True, 0

    def reset(self, key: str | None = None) -> None:
        """Test helper. Clear one key, or everything if key is None."""
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)


_limiter: RateLimiter | None = None
_limiter_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is not None:
        return _limiter

    with _limiter_lock:
        if _limiter is not None:
            return _limiter

        settings = get_settings()
        backend = getattr(settings, "RATE_LIMITER_BACKEND", "memory")
        if backend == "memory":
            _limiter = InMemoryRateLimiter()
        elif backend == "redis":
            raise NotImplementedError(
                "Redis rate-limiter backend not implemented yet. "
                "Implement a class with the RateLimiter protocol and register it here."
            )
        else:
            raise ValueError(f"Unknown RATE_LIMITER_BACKEND: {backend!r}")
    return _limiter


__all__ = ["RateLimiter", "InMemoryRateLimiter", "get_rate_limiter"]