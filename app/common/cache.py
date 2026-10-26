"""Tiny in-process TTL cache used for the admin dashboard.

Kept behind this interface so the storage can be swapped for Redis later
without touching any caller. Thread-safe because Uvicorn may run sync
handlers in a threadpool.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Hashable


class TTLCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = int(ttl_seconds)
        self._store: dict[Hashable, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if now >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: Hashable, value: Any) -> None:
        expires_at = time.monotonic() + self.ttl
        with self._lock:
            self._store[key] = (value, expires_at)

    def get_or_set(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


__all__ = ["TTLCache"]