"""Local cross-encoder reranker (no external API call, low latency).

Runs a small sentence-transformers cross-encoder model in-process; kept out
of the request's critical path cost by operating only on the already-small
candidate_pool produced by hybrid retrieval, not the whole corpus.
"""
from __future__ import annotations

from sentence_transformers import CrossEncoder

from bank_rag.domain.entities import Chunk


class CrossEncoderReranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self._model = CrossEncoder(model_name)

    async def rerank(self, query: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
        if not chunks:
            return []
        pairs = [(query, chunk.text) for chunk in chunks]
        scores = self._model.predict(pairs)
        ranked = [c for _, c in sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)]
        return ranked[:top_k]
