"""Segments a DOCX by heading structure: each Heading paragraph starts a new
section, accumulating following paragraphs until the next heading. The
locator value is a breadcrumb path (e.g. "Conti correnti > Conto Base"), so
a no-index rule can exclude one section of a document without touching
the rest.
"""
from __future__ import annotations

import io

from docx import Document as DocxDocument

from bank_rag.domain.entities import ChunkLocator, DocumentSegment

_HEADING_LEVELS = {"Title": 1, "Heading 1": 1, "Heading 2": 2, "Heading 3": 3, "Heading 4": 4}


def segment_docx(content: bytes) -> list[DocumentSegment]:
    document = DocxDocument(io.BytesIO(content))
    segments: list[DocumentSegment] = []
    heading_stack: list[tuple[int, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            path = " > ".join(title for _, title in heading_stack) or "documento"
            segments.append(DocumentSegment(text=text, locator=ChunkLocator(kind="section", value=path)))
        buffer.clear()

    for paragraph in document.paragraphs:
        level = _HEADING_LEVELS.get(paragraph.style.name if paragraph.style else "")
        title = paragraph.text.strip()
        if level and title:
            flush()
            heading_stack = [h for h in heading_stack if h[0] < level] + [(level, title)]
        elif title:
            buffer.append(paragraph.text)

    flush()
    return segments
