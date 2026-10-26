"""TTL cache with single-flight fetches and stale-if-error.
N concurrent viewers of a game cost one upstream request per TTL."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from .sources import NotAvailable, UpstreamError

log = logging.getLogger("nbadash.cache")


class TTLCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._data: dict[str, tuple[float, Any]] = {}  # key -> (expires_at, value)
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, key: str, fetch: Callable[[], Awaitable[Any]],
                  ttl: Callable[[Any], float]) -> Any:
        hit = self._data.get(key)
        if hit and hit[0] > self._clock():
            return hit[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            hit = self._data.get(key)  # another waiter may have refreshed it
            if hit and hit[0] > self._clock():
                return hit[1]
            try:
                value = await fetch()
            except UpstreamError as e:
                if hit:  # serve stale rather than failing the page
                    log.warning("serving stale %s: %s", key, e)
                    return hit[1]
                raise
            except NotAvailable:
                raise
            self._data[key] = (self._clock() + ttl(value), value)
            return value
