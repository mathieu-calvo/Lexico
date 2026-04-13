"""In-memory LRU cache with TTL for hot-path access."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass
class _Entry:
    data: Any
    expires_at: float


class MemoryCache:
    """LRU + TTL. Generic over any picklable payload."""

    def __init__(self, max_size: int = 1024, default_ttl_hours: int = 24) -> None:
        self._max_size = max_size
        self._default_ttl_seconds = default_ttl_hours * 3600
        self._store: OrderedDict[str, _Entry] = OrderedDict()

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return entry.data

    def put(self, key: str, data: Any, ttl_hours: int | None = None) -> None:
        ttl = (ttl_hours * 3600) if ttl_hours else self._default_ttl_seconds
        self._store[key] = _Entry(data=data, expires_at=time.monotonic() + ttl)
        self._store.move_to_end(key)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
