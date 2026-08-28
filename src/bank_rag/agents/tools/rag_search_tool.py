"""The primary knowledge tool: hybrid retrieval + rerank + citation building.

This is where "RAG" actually lives. It is deliberately just a Tool among
others — the Router Agent decides *whether* to call it, which is what makes
the system "agentic" rather than a fixed retrieve-then-generate pipeline.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, ClassVar

from bank_rag.application.ports.embedder import Embedder
from bank_rag.application.ports.keyword_index import KeywordIndex
from bank_rag.application.ports.reranker import Reranker
from bank_rag.application.ports.vector_store import VectorStore
from bank_rag.domain.entities import Audience, Chunk, Citation


def _reciprocal_rank_fusion(*ranked_lists: list[Chunk], k: int = 60) -> list[Chunk]:
    scores: dict[str, float] = {}
    by_id: dict[str, Chunk] = {}
    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked):
            key = str(chunk.id)
            by_id[key] = chunk
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
    ordered_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [by_id[cid] for cid in ordered_ids]


class RagSearchTool:
    name = "search_knowledge_base"
    description = (
        "Searches the bank's indexed public FAQs, product sheets and internal "
        "employee-uploaded documents. Use this whenever the customer asks about "
        "products, rates, procedures or policies."
    )
    parameters_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "search query"}},
        "required": ["query"],
    }
    requires_authentication = False
    requires_confirmation = False  # a read-only search; nothing to confirm

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        keyword_index: KeywordIndex,
        reranker: Reranker,
        allowed_audiences: list[Audience],
        top_k: int = 5,
        candidate_pool: int = 15,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store
        self._keyword_index = keyword_index
        self._reranker = reranker
        self._allowed_audiences = allowed_audiences
        self._top_k = top_k
        self._candidate_pool = candidate_pool

    async def run(self, query: str) -> str:
        try:
            citations = await self.search(query)
        except Exception as exc:  # noqa: BLE001 - must degrade gracefully, not crash the agent loop
            return json.dumps({"error": f"retrieval_failed: {exc}"})
        if not citations:
            return json.dumps({"results": [], "note": "no relevant documents found"})
        return json.dumps({"results": [asdict(c) for c in citations]})

    async def search(self, query: str) -> list[Citation]:
        query_embedding = await self._embedder.embed_query(query)
        vector_hits, keyword_hits = await self._gather(query, query_embedding)
        fused = _reciprocal_rank_fusion(vector_hits, keyword_hits)[: self._candidate_pool]
        reranked = await self._reranker.rerank(query, fused, top_k=self._top_k)
        return [
            Citation(
                document_id=c.document_id,
                title=c.metadata.title,
                snippet=c.text[:300],
                score=1.0,
            )
            for c in reranked
        ]

    async def _gather(
        self, query: str, query_embedding: list[float]
    ) -> tuple[list[Chunk], list[Chunk]]:
        vector_hits = await self._vector_store.search(
            query_embedding, top_k=self._candidate_pool, allowed_audiences=self._allowed_audiences
        )
        keyword_hits = await self._keyword_index.search(
            query, top_k=self._candidate_pool, allowed_audiences=self._allowed_audiences
        )
        return vector_hits, keyword_hits

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }
