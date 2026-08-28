"""Use case: IngestDocument. Called by the employee-facing admin upload flow
and by the scheduled website sync (ingestion/pipeline.py).

Handles versioning: a re-upload of the same source_id purges the previous
version's chunks from both indexes before writing the new ones, so search
results never mix stale and current content for the same document.

Handles granular no-index: the document as a whole is checked first (refuses
to ingest anything if the whole source_id is excluded); each DocumentSegment
is then checked individually, so excluding one page/section/row-range still
lets the rest of the document through.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from bank_rag.application.ports.content_sanitizer import ContentSanitizer
from bank_rag.application.ports.document_repository import DocumentRepository
from bank_rag.application.ports.embedder import Embedder
from bank_rag.application.ports.keyword_index import KeywordIndex
from bank_rag.application.ports.noindex_registry import NoIndexRegistry
from bank_rag.application.ports.vector_store import VectorStore
from bank_rag.domain.entities import Audience, Chunk, DocumentMetadata, DocumentSegment
from bank_rag.ingestion.chunking.semantic_chunker import SemanticChunker


class DocumentExcludedError(Exception):
    """Raised when source_id matches an active whole-document no-index rule
    (see ManageNoIndexRules) — ingestion refuses to (re-)index it at all.
    A segment-scoped rule does NOT raise this; it silently excludes only the
    matching segments (see execute()).
    """


class IngestDocument:
    def __init__(
        self,
        chunker: SemanticChunker,
        embedder: Embedder,
        vector_store: VectorStore,
        keyword_index: KeywordIndex,
        document_repository: DocumentRepository,
        content_sanitizer: ContentSanitizer,
        noindex_registry: NoIndexRegistry,
    ) -> None:
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store
        self._keyword_index = keyword_index
        self._documents = document_repository
        self._sanitizer = content_sanitizer
        self._noindex = noindex_registry

    async def execute(
        self,
        source_id: str,
        title: str,
        segments: list[DocumentSegment],
        audience: Audience,
        uploaded_by: str,
    ) -> int:
        if await self._noindex.is_excluded(source_id):
            raise DocumentExcludedError(
                f"'{source_id}' è escluso dall'indicizzazione da una regola no-index attiva"
            )

        previous_version = await self._documents.get_latest_version(source_id)
        if previous_version > 0:
            await self._vector_store.delete_by_document(source_id)
            await self._keyword_index.delete_by_document(source_id)

        metadata = DocumentMetadata(
            source_id=source_id,
            title=title,
            audience=audience,
            uploaded_by=uploaded_by,
            version=previous_version + 1,
            updated_at=datetime.now(UTC),
        )

        included_segments = [
            DocumentSegment(text=self._sanitizer.sanitize(segment.text), locator=segment.locator)
            for segment in segments
            if not await self._noindex.is_excluded(source_id, segment.locator)
        ]

        chunk_pairs = self._chunker.split_segments(included_segments)
        texts = [text for text, _ in chunk_pairs]
        embeddings = await self._embedder.embed_documents(texts) if texts else []
        chunks = [
            Chunk(id=uuid4(), document_id=source_id, text=text, metadata=metadata, locator=locator, embedding=vector)
            for (text, locator), vector in zip(chunk_pairs, embeddings)
        ]

        if chunks:
            await self._vector_store.upsert(chunks)
            await self._keyword_index.index(chunks)
        await self._documents.save_metadata(metadata)
        return len(chunks)
