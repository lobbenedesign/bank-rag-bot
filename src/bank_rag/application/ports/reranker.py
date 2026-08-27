"""Port for a cross-encoder reranker applied after hybrid retrieval.

Retrieval gives ~top_k*3 candidates cheaply (bi-encoder / BM25); the reranker
re-scores that shortlist with a more expensive, more accurate cross-encoder
and keeps only top_k. This is what actually improves answer grounding quality
in production RAG systems, and it's the step most take-home/interview answers skip.
"""
from __future__ import annotations

from typing import Protocol

from bank_rag.domain.entities import Chunk


class Reranker(Protocol):
    async def rerank(self, query: str, chunks: list[Chunk], top_k: int) -> list[Chunk]: ...
