"""Rate-limit state and synchronization for the HTTP layer.

The :class:`RateLimitManager` owns:

* per-route :class:`RateLimitInfo` snapshots derived from response headers;
* per-route asyncio locks (so concurrent requests to the same bucket
  don't trample one another);
* a single global lock that pauses every route while a global rate limit
  window is active.

Splitting this state out of :class:`vaidcord.http.client.HTTPClient` makes
the manager unit-testable and lets future transports (mock, alternative
async runtimes) reuse the exact same policy.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from .config import RateLimitInfo

logger = logging.getLogger(__name__)


class RateLimitManager:
    """Owns Discord route/global rate-limit state and synchronization."""

    def __init__(self) -> None:
        self.limits: dict[str, RateLimitInfo] = {}
        self.global_reset: datetime | None = None
        self._global_lock = asyncio.Lock()
        self._route_locks: dict[str, asyncio.Lock] = {}

    def get_route_lock(self, endpoint: str) -> asyncio.Lock:
        lock = self._route_locks.get(endpoint)
        if lock is None:
            lock = asyncio.Lock()
            self._route_locks[endpoint] = lock
        return lock

    def update_route(self, endpoint: str, info: RateLimitInfo) -> None:
        self.limits[endpoint] = info

    def update_global(self, reset: datetime) -> None:
        self.global_reset = reset

    async def wait_for_global(self) -> None:
        async with self._global_lock:
            if self.global_reset and datetime.now() < self.global_reset:
                wait_time = (self.global_reset - datetime.now()).total_seconds()
                logger.warning(f"Waiting for global rate limit: {wait_time}s")
                await asyncio.sleep(wait_time)


__all__ = ["RateLimitManager"]
