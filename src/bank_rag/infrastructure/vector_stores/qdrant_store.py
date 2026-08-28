"""Concrete adapter for the VectorStore port, backed by Qdrant.

Note the audience filter is applied as a Qdrant `must` filter in the query
itself (server-side), not in Python after fetching results — a document
marked INTERNAL is physically never returned to a request that only allows
PUBLIC, regardless of application-code bugs downstream.
"""
from __future__ import annotations

from datetime import UTC, datetime
from fnmatch import fnmatch
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from bank_rag.domain.entities import Audience, Chunk, ChunkLocator, DocumentMetadata


class QdrantVectorStore:
    def __init__(self, client: AsyncQdrantClient, collection_name: str) -> None:
        self._client = client
        self._collection = collection_name

    async def upsert(self, chunks: list[Chunk]) -> None:
        points = [
            models.PointStruct(
                id=str(chunk.id),
                vector=chunk.embedding,
                payload={
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "audience": chunk.metadata.audience.value,
                    "title": chunk.metadata.title,
                    "version": chunk.metadata.version,
                    "locator_kind": chunk.locator.kind,
                    "locator_value": chunk.locator.value,
                },
            )
            for chunk in chunks
        ]
        await self._client.upsert(collection_name=self._collection, points=points)

    async def delete_by_document(self, document_id: str) -> None:
        await self._client.delete(
            collection_name=self._collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
                )
            ),
        )

    async def delete_by_locator(self, document_id: str, locator_kind: str, locator_pattern: str) -> int:
        # Qdrant filters do exact/set matching, not glob — so the document_id
        # + locator_kind narrowing happens server-side, and the glob match on
        # locator_value happens client-side on that (small) candidate set.
        points, _ = await self._client.scroll(
            collection_name=self._collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id)),
                    models.FieldCondition(key="locator_kind", match=models.MatchValue(value=locator_kind)),
                ]
            ),
            limit=10_000,
            with_payload=True,
        )
        matching_ids = [
            p.id for p in points if fnmatch((p.payload or {}).get("locator_value", ""), locator_pattern)
        ]
        if matching_ids:
            await self._client.delete(
                collection_name=self._collection, points_selector=models.PointIdsList(points=matching_ids)
            )
        return len(matching_ids)

    async def search(
        self, query_embedding: list[float], top_k: int, allowed_audiences: list[Audience]
    ) -> list[Chunk]:
        result = await self._client.search(
            collection_name=self._collection,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="audience",
                        match=models.MatchAny(any=[a.value for a in allowed_audiences]),
                    )
                ]
            ),
        )
        return [self._to_chunk(point) for point in result]

    @staticmethod
    def _to_chunk(point) -> Chunk:
        payload = point.payload or {}
        metadata = DocumentMetadata(
            source_id=payload["document_id"],
            title=payload.get("title", ""),
            audience=Audience(payload["audience"]),
            uploaded_by=None,
            version=payload.get("version", 1),
            updated_at=datetime.now(UTC),
        )
        locator = ChunkLocator(kind=payload.get("locator_kind", "whole"), value=payload.get("locator_value", "document"))
        return Chunk(
            id=UUID(str(point.id)), document_id=payload["document_id"], text=payload.get("text", ""),
            metadata=metadata, locator=locator,
        )
