"""Concrete adapter for the VectorStore port, backed by Qdrant.

Note the audience filter is applied as a Qdrant `must` filter in the query
itself (server-side), not in Python after fetching results — a document
marked INTERNAL is physically never returned to a request that only allows
PUBLIC, regardless of application-code bugs downstream. The same reasoning
applies to `valid_until`: an expired chunk is excluded by the database
query, not by an `if` in application code that a future refactor could
accidentally drop.

Real bug found and fixed here (2026-08-28): this file called
`AsyncQdrantClient.search()`, which qdrant-client actually removed as of a
version well within this project's own `qdrant-client>=1.10` pin (verified
by installing the dependency for real, not just reading the pinned range —
`pip install qdrant-client` resolves to 1.19.0 today, where `.search()` no
longer exists on `AsyncQdrantClient` at all). Every unit test in this repo
mocks `QdrantVectorStore` and never imports the real `qdrant_client`
package, so nothing here could have caught it short of actually installing
the real dependency and inspecting it — which is what surfaced this.
Migrated to `.query_points()`, the current replacement, which returns a
`QueryResponse.points` instead of a plain list.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from fnmatch import fnmatch
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from bank_rag.domain.entities import Audience, Chunk, ChunkLocator, DocumentMetadata

# Sentinel for "no expiry" — stored as a real, always-present integer instead
# of a missing/null payload field. Found by actually running this filter
# against qdrant-client's own `:memory:` test backend (not just reasoning
# about the Qdrant filter DSL): `FieldCondition(is_null=True)` — the
# textbook way to express "OR no expiry set" — silently matched ZERO points
# there, including points where the field was entirely absent from the
# payload, which is precisely what it's documented to match. Whether that's
# a real-server difference or a local-mode-only gap wasn't verifiable here
# (no live Qdrant server to test against), so this design sidesteps the
# primitive entirely rather than ship a filter proven unreliable, real
# server or not: every point always has a concrete `valid_until_ts`
# (this far-future sentinel when no expiry is set), so the query is always
# a single unconditional `range(gte=now)` — no null-handling, no nested
# `should`, nothing left to get subtly wrong across qdrant-client versions.
_NO_EXPIRY_SENTINEL = int(datetime(9999, 12, 31, tzinfo=UTC).timestamp())


def _valid_until_ts(valid_until: date | None) -> int:
    """Payload is stored as a Unix timestamp (UTC midnight), not an ISO
    string: a plain integer `Range` filter works identically across Qdrant
    client versions, where date/datetime range-filter support has shifted
    more than once — one less compatibility surface to track."""
    if valid_until is None:
        return _NO_EXPIRY_SENTINEL
    return int(datetime(valid_until.year, valid_until.month, valid_until.day, tzinfo=UTC).timestamp())


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
                    "valid_until_ts": _valid_until_ts(chunk.metadata.valid_until),
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
        self,
        query_embedding: list[float],
        top_k: int,
        allowed_audiences: list[Audience],
        score_threshold: float | None = None,
    ) -> list[Chunk]:
        now_ts = int(datetime.now(UTC).timestamp())
        result = await self._client.query_points(
            collection_name=self._collection,
            query=query_embedding,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="audience",
                        match=models.MatchAny(any=[a.value for a in allowed_audiences]),
                    ),
                    # Every point always carries a concrete valid_until_ts
                    # (the far-future sentinel when no expiry was set — see
                    # module docstring), so this is always a plain range
                    # condition, never a null check.
                    models.FieldCondition(key="valid_until_ts", range=models.Range(gte=now_ts)),
                ]
            ),
        )
        return [self._to_chunk(point) for point in result.points]

    @staticmethod
    def _to_chunk(point) -> Chunk:
        payload = point.payload or {}
        valid_until_ts = payload.get("valid_until_ts")
        has_real_expiry = valid_until_ts is not None and valid_until_ts != _NO_EXPIRY_SENTINEL
        metadata = DocumentMetadata(
            source_id=payload["document_id"],
            title=payload.get("title", ""),
            audience=Audience(payload["audience"]),
            uploaded_by=None,
            version=payload.get("version", 1),
            updated_at=datetime.now(UTC),
            valid_until=datetime.fromtimestamp(valid_until_ts, tz=UTC).date() if has_real_expiry else None,
        )
        locator = ChunkLocator(kind=payload.get("locator_kind", "whole"), value=payload.get("locator_value", "document"))
        return Chunk(
            id=UUID(str(point.id)), document_id=payload["document_id"], text=payload.get("text", ""),
            metadata=metadata, locator=locator,
        )
