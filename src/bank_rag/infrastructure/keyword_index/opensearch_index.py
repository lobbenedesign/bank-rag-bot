"""BM25 lexical search adapter, backed by OpenSearch (drop-in for Elasticsearch).

Kept as its own index rather than "just use the vector DB's filter" because
lexical (term-exact) search and semantic (embedding) search fail on different
query shapes; hybrid retrieval fuses both (see agents/tools/rag_search_tool.py).
"""
from __future__ import annotations

from datetime import datetime, timezone
from fnmatch import fnmatch
from uuid import UUID

from opensearchpy import AsyncOpenSearch

from bank_rag.domain.entities import Audience, Chunk, ChunkLocator, DocumentMetadata


class OpenSearchKeywordIndex:
    def __init__(self, client: AsyncOpenSearch, index_name: str) -> None:
        self._client = client
        self._index = index_name

    async def index(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            await self._client.index(
                index=self._index,
                id=str(chunk.id),
                body={
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "audience": chunk.metadata.audience.value,
                    "title": chunk.metadata.title,
                    "version": chunk.metadata.version,
                    "locator_kind": chunk.locator.kind,
                    "locator_value": chunk.locator.value,
                },
            )

    async def delete_by_document(self, document_id: str) -> None:
        await self._client.delete_by_query(
            index=self._index,
            body={"query": {"term": {"document_id": document_id}}},
        )

    async def delete_by_locator(self, document_id: str, locator_kind: str, locator_pattern: str) -> int:
        # Same approach as the Qdrant adapter: narrow server-side by
        # document_id + locator_kind (exact terms), glob-match locator_value
        # client-side on that candidate set, then delete by explicit ids.
        response = await self._client.search(
            index=self._index,
            body={
                "size": 10_000,
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"document_id": document_id}},
                            {"term": {"locator_kind": locator_kind}},
                        ]
                    }
                },
            },
        )
        matching_ids = [
            hit["_id"] for hit in response["hits"]["hits"]
            if fnmatch(hit["_source"].get("locator_value", ""), locator_pattern)
        ]
        for doc_id in matching_ids:
            await self._client.delete(index=self._index, id=doc_id)
        return len(matching_ids)

    async def search(self, query_text: str, top_k: int, allowed_audiences: list[Audience]) -> list[Chunk]:
        response = await self._client.search(
            index=self._index,
            body={
                "size": top_k,
                "query": {
                    "bool": {
                        "must": [{"match": {"text": query_text}}],
                        "filter": [{"terms": {"audience": [a.value for a in allowed_audiences]}}],
                    }
                },
            },
        )
        return [self._to_chunk(hit) for hit in response["hits"]["hits"]]

    @staticmethod
    def _to_chunk(hit: dict) -> Chunk:
        source = hit["_source"]
        metadata = DocumentMetadata(
            source_id=source["document_id"],
            title=source.get("title", ""),
            audience=Audience(source["audience"]),
            uploaded_by=None,
            version=source.get("version", 1),
            updated_at=datetime.now(timezone.utc),
        )
        locator = ChunkLocator(kind=source.get("locator_kind", "whole"), value=source.get("locator_value", "document"))
        return Chunk(
            id=UUID(hit["_id"]), document_id=source["document_id"], text=source.get("text", ""),
            metadata=metadata, locator=locator,
        )
