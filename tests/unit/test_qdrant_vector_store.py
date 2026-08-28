"""Real integration test for QdrantVectorStore — against qdrant-client's own
in-process `:memory:` backend, not a mock. This is deliberate: the bug this
file exists to catch (`.search()` silently removed from `AsyncQdrantClient`
in a version within this project's own `qdrant-client>=1.10` pin — see
qdrant_store.py's module docstring) is exactly the class of bug a mock can
never catch, because a mock only proves "the code calls some method",
never "that method actually exists on the real installed client". `:memory:`
is qdrant-client's own supported local mode (same client class, no network,
no server process) — real query/filter/scoring logic runs for real here.
"""
from __future__ import annotations

import uuid
from datetime import UTC as _UTC
from datetime import date, timedelta
from datetime import datetime as _datetime

import pytest
from qdrant_client import AsyncQdrantClient, models

from bank_rag.domain.entities import Audience, Chunk, ChunkLocator, DocumentMetadata
from bank_rag.infrastructure.vector_stores.qdrant_store import QdrantVectorStore

COLLECTION = "test_documents"


async def _new_store() -> QdrantVectorStore:
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE),
    )
    return QdrantVectorStore(client, COLLECTION)


def _chunk(text: str, audience: Audience, vector: list[float], valid_until: date | None = None) -> Chunk:
    metadata = DocumentMetadata(
        source_id="doc-1", title="Mutuo Giovani", audience=audience, uploaded_by="mario",
        version=1, updated_at=_datetime.now(_UTC), valid_until=valid_until,
    )
    return Chunk(
        id=uuid.uuid4(), document_id="doc-1", text=text, metadata=metadata,
        locator=ChunkLocator(kind="page", value="1"), embedding=vector,
    )


@pytest.mark.asyncio
async def test_search_actually_runs_against_the_real_client_without_crashing():
    """Would have caught the real .search()-removed bug immediately: a mock
    of QdrantVectorStore.search can never fail this way, only the real
    AsyncQdrantClient can."""
    store = await _new_store()
    await store.upsert([_chunk("Tasso fisso 3.25%.", Audience.PUBLIC, [1.0, 0.0, 0.0])])

    results = await store.search([1.0, 0.0, 0.0], top_k=5, allowed_audiences=[Audience.PUBLIC])

    assert len(results) == 1
    assert results[0].text == "Tasso fisso 3.25%."


@pytest.mark.asyncio
async def test_internal_chunk_never_returned_to_public_only_search():
    store = await _new_store()
    await store.upsert(
        [
            _chunk("Nota interna: margine 0.5%.", Audience.INTERNAL, [1.0, 0.0, 0.0]),
            _chunk("FAQ pubblica sul mutuo.", Audience.PUBLIC, [1.0, 0.0, 0.0]),
        ]
    )

    results = await store.search([1.0, 0.0, 0.0], top_k=10, allowed_audiences=[Audience.PUBLIC])

    assert len(results) == 1
    assert results[0].text == "FAQ pubblica sul mutuo."


@pytest.mark.asyncio
async def test_expired_chunk_is_excluded_even_when_audience_matches():
    store = await _new_store()
    expired = _datetime.now(_UTC).date() - timedelta(days=1)
    await store.upsert(
        [
            _chunk("Promo scaduta: tasso 1.99%.", Audience.PUBLIC, [1.0, 0.0, 0.0], valid_until=expired),
            _chunk("Tasso standard 3.25%.", Audience.PUBLIC, [1.0, 0.0, 0.0]),
        ]
    )

    results = await store.search([1.0, 0.0, 0.0], top_k=10, allowed_audiences=[Audience.PUBLIC])

    assert len(results) == 1
    assert results[0].text == "Tasso standard 3.25%."


@pytest.mark.asyncio
async def test_chunk_valid_until_a_future_date_is_still_returned():
    store = await _new_store()
    future = _datetime.now(_UTC).date() + timedelta(days=30)
    await store.upsert([_chunk("Promo attiva: tasso 1.99%.", Audience.PUBLIC, [1.0, 0.0, 0.0], valid_until=future)])

    results = await store.search([1.0, 0.0, 0.0], top_k=10, allowed_audiences=[Audience.PUBLIC])

    assert len(results) == 1
    assert results[0].metadata.valid_until == future


@pytest.mark.asyncio
async def test_score_threshold_drops_dissimilar_candidates():
    store = await _new_store()
    await store.upsert(
        [
            _chunk("Vettore identico alla query.", Audience.PUBLIC, [1.0, 0.0, 0.0]),
            _chunk("Vettore ortogonale, similarità nulla.", Audience.PUBLIC, [0.0, 1.0, 0.0]),
        ]
    )

    results = await store.search(
        [1.0, 0.0, 0.0], top_k=10, allowed_audiences=[Audience.PUBLIC], score_threshold=0.5
    )

    assert len(results) == 1
    assert results[0].text == "Vettore identico alla query."
