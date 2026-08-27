from __future__ import annotations

from typing import Protocol

from bank_rag.domain.entities import ChunkLocator, NoIndexRule


class NoIndexRegistry(Protocol):
    async def add_rule(self, rule: NoIndexRule) -> None: ...

    async def remove_rule(self, pattern: str) -> None: ...

    async def list_rules(self) -> list[NoIndexRule]: ...

    async def is_excluded(self, identifier: str, locator: ChunkLocator | None = None) -> bool:
        """identifier is a URL for web pages or a source_id (filename) for
        uploaded documents. A rule with no locator excludes the whole
        document regardless of `locator`. A rule with a locator only excludes
        when `locator` is given and matches both kind and pattern — so
        calling with locator=None checks only whole-document rules, which is
        exactly the pre-flight check IngestDocument does before touching a
        source at all.
        """
        ...
