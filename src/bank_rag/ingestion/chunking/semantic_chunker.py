"""Splits raw text into overlapping, sentence-aware chunks.

Naive fixed-size splitting cuts sentences (and numbers/rates) in half, which
is exactly what you don't want in a banking document. This chunker keeps
sentence boundaries and adds overlap so a fact near a chunk edge still has
context on both sides.

Context prepending (the "orphan chunk" problem): a chunk that only says
"la commissione di estinzione anticipata è dell'1%" is useless once it's
been pulled out of the document that gave it a subject — the embedding
itself never captured *which* product's fee that is. Every chunk is
prefixed with `[Documento: {title} | {locator}]` before embedding and
storage, so the vector — and the citation the customer eventually sees —
both carry the document/section identity, not just the isolated sentence.
"""
from __future__ import annotations

import re

from bank_rag.domain.entities import ChunkLocator, DocumentSegment


class SemanticChunker:
    def __init__(self, max_chars: int = 800, overlap_chars: int = 150) -> None:
        self._max_chars = max_chars
        self._overlap_chars = overlap_chars

    def split_segments(self, segments: list[DocumentSegment], title: str = "") -> list[tuple[str, ChunkLocator]]:
        """Chunks each segment's text independently, tagging every resulting
        chunk with that segment's locator. A long segment can still produce
        several chunks sharing one locator — the locator is the smallest
        addressable unit for no-index exclusion, not a 1:1 chunk boundary.

        `title` (the document's title, when known) is prepended to every
        chunk produced — see module docstring. Left empty, chunks are
        produced exactly as before (no prefix), which is what every
        existing caller/test that doesn't pass `title` still gets.
        """
        return [
            (self._with_context(chunk_text, title, segment.locator), segment.locator)
            for segment in segments
            for chunk_text in self.split(segment.text)
        ]

    @staticmethod
    def _with_context(chunk_text: str, title: str, locator: ChunkLocator) -> str:
        if not title:
            return chunk_text
        location = "" if locator.kind == "whole" else f" | {locator.kind}: {locator.value}"
        return f"[Documento: {title}{location}] {chunk_text}"

    def split(self, text: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= self._max_chars:
                current = f"{current} {sentence}".strip()
                continue
            if current:
                chunks.append(current)
            current = self._overlap_tail(current) + " " + sentence if chunks else sentence
            current = current.strip()

        if current:
            chunks.append(current)
        return [c for c in chunks if c]

    def _overlap_tail(self, text: str) -> str:
        return text[-self._overlap_chars:] if len(text) > self._overlap_chars else text
