from __future__ import annotations

from typing import Protocol

from bank_rag.domain.entities import DocumentMetadata


class DocumentRepository(Protocol):
    """System-of-record for document metadata/versioning (relational DB).

    The vector store and keyword index hold derived, disposable data — they
    can always be rebuilt from here. This is what makes re-ingestion and
    version invalidation safe instead of accumulating stale duplicate chunks.
    """

    async def save_metadata(self, metadata: DocumentMetadata) -> None: ...

    async def get_latest_version(self, source_id: str) -> int: ...

    async def list_by_audience(self, audience: str) -> list[DocumentMetadata]: ...

    async def list_all(self) -> list[DocumentMetadata]: ...
