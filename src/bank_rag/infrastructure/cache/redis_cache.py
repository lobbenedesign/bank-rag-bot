from __future__ import annotations

from redis.asyncio import Redis


class RedisResponseCache:
    def __init__(self, redis: Redis, namespace: str = "answer_cache") -> None:
        self._redis = redis
        self._namespace = namespace

    async def get(self, key: str) -> str | None:
        return await self._redis.get(f"{self._namespace}:{key}")

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self._redis.set(f"{self._namespace}:{key}", value, ex=ttl_seconds)
