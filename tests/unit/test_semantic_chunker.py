from __future__ import annotations

from bank_rag.ingestion.chunking.semantic_chunker import SemanticChunker


def test_does_not_split_mid_sentence():
    text = "Il Conto Base non ha canone. Il TAEG del mutuo è 3.5%. " * 20
    chunker = SemanticChunker(max_chars=100, overlap_chars=20)

    chunks = chunker.split(text)

    assert len(chunks) > 1
    assert all(chunk.strip().endswith((".", "%")) for chunk in chunks)


def test_empty_text_returns_no_chunks():
    assert SemanticChunker().split("") == []
