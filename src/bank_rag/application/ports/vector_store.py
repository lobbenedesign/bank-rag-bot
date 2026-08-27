"""Port: hexagonal boundary towards any vector database (Qdrant, Milvus, Pinecone...).

The application layer depends only on this Protocol, never on a concrete SDK.
Swapping Qdrant for Milvus means writing one new adapter in `infrastructure/`,
zero changes here or in the agents/use-cases layer.
"""
from __future__ import annotations

from typing import Protocol

from bank_rag.domain.entities import Audience, Chunk


class VectorStore(Protocol):
    async def upsert(self, chunks: list[Chunk]) -> None: ...

    async def delete_by_document(self, document_id: str) -> None:
        """Used by re-ingestion to purge stale chunks of a previous document version."""
        ...

    async def delete_by_locator(self, document_id: str, locator_kind: str, locator_pattern: str) -> int:
        """Purges only the chunks of `document_id` whose locator matches
        (locator_kind, locator_pattern) — used for granular no-index
        exclusion (a single page/section/row-range), not the whole document.
        Returns the number of chunks deleted.
        """
        ...

    async def search(
        self,
        query_embedding: list[float],
        top_k: int,
        allowed_audiences: list[Audience],
    ) -> list[Chunk]:
        """Vector similarity search, pre-filtered by audience at the DB level
        (metadata filter), never post-filtered in application code — a chunk
        the caller is not allowed to see must never leave the store.
        """
        ...
