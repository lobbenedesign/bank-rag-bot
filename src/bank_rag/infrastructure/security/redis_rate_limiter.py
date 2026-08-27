"""Fixed-window rate limiter backed by Redis INCR/EXPIRE.

Fixed-window is simpler than sliding-window/token-bucket and good enough for
protecting the LLM/retrieval cost on /chat and /admin/documents — the goal
is capping abuse and runaway cost, not exact per-second fairness.
"""
from __future__ import annotations

from redis.asyncio import Redis


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        full_key = f"ratelimit:{key}:{window_seconds}"
        count = await self._redis.incr(full_key)
        if count == 1:
            await self._redis.expire(full_key, window_seconds)
        return count <= limit
