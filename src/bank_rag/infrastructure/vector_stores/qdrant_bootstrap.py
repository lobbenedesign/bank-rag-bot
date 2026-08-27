"""Provisions the Qdrant collection with a production-grade schema.

Run once per environment (idempotent — safe to re-run in CI/CD on every
deploy): `python -m bank_rag.infrastructure.vector_stores.qdrant_bootstrap`

Design choices, not defaults, and why:
- distance=COSINE, size=1536: matches `text-embedding-3-small`. Changing the
  embedding model means provisioning a NEW collection, never mutating this
  one — old and new vectors are not comparable, and mixing them silently
  corrupts retrieval.
- hnsw m/ef_construct raised above Qdrant's defaults: better recall for a
  corpus in the hundreds-of-thousands of chunks range, at a small memory cost.
- scalar quantization: cuts HNSW index RAM by up to ~4x with a small recall
  hit — matters once this runs 24/7 in production, not just in a demo.
- payload indexes on audience/document_id/version: without these, the RBAC
  filter applied in every `search()` call (see qdrant_store.py) degrades to
  a linear scan instead of using an index. This is the single most common
  reason a "working" vector DB search gets slow under real load.
"""
from __future__ import annotations

import asyncio

from qdrant_client import AsyncQdrantClient, models

from bank_rag.config.settings import get_settings

EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small


async def ensure_collection(client: AsyncQdrantClient, collection_name: str) -> None:
    if await client.collection_exists(collection_name):
        return

    await client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=EMBEDDING_DIMENSIONS,
            distance=models.Distance.COSINE,
            hnsw_config=models.HnswConfigDiff(m=32, ef_construct=200),
        ),
        quantization_config=models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(
                type=models.ScalarType.INT8, quantile=0.99, always_ram=True
            )
        ),
    )

    for field_name, schema in (
        ("audience", models.PayloadSchemaType.KEYWORD),
        ("document_id", models.PayloadSchemaType.KEYWORD),
        ("version", models.PayloadSchemaType.INTEGER),
    ):
        await client.create_payload_index(
            collection_name=collection_name, field_name=field_name, field_schema=schema
        )


async def main() -> None:
    settings = get_settings()
    client = AsyncQdrantClient(url=settings.qdrant_url)
    await ensure_collection(client, settings.qdrant_collection)


if __name__ == "__main__":
    asyncio.run(main())
