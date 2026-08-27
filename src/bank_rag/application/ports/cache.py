from __future__ import annotations

from typing import Protocol


class ResponseCache(Protocol):
    """Caches (normalized_question -> answer) for frequent FAQ-style queries,
    to avoid re-running embedding + retrieval + LLM generation each time.
    """

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...
