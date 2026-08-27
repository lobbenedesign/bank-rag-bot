"""Port for lexical/BM25 search, used alongside vector search for hybrid retrieval.

Pure vector similarity misses exact terms that matter a lot in banking documents
(product codes, "TAEG", "IBAN", article numbers). Hybrid retrieval (BM25 + vector,
merged with reciprocal rank fusion) consistently outperforms vector-only RAG on
this kind of structured/technical text.
"""
from __future__ import annotations

from typing import Protocol

from bank_rag.domain.entities import Audience, Chunk


class KeywordIndex(Protocol):
    async def index(self, chunks: list[Chunk]) -> None: ...

    async def delete_by_document(self, document_id: str) -> None: ...

    async def delete_by_locator(self, document_id: str, locator_kind: str, locator_pattern: str) -> int:
        """See VectorStore.delete_by_locator — same contract, lexical index side."""
        ...

    async def search(
        self,
        query_text: str,
        top_k: int,
        allowed_audiences: list[Audience],
    ) -> list[Chunk]: ...
