"""Segments Markdown by heading (# ## ###...) into a breadcrumb-addressed
section per heading. Also provides the plain-text fallback (fixed-size line
ranges) used both when a .md file has no headings and for plain .txt files,
which have no structure to key a locator on other than line position.
"""
from __future__ import annotations

import re

from bank_rag.domain.entities import ChunkLocator, DocumentSegment

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_LINE_RANGE_SIZE = 40


def segment_markdown(content: bytes) -> list[DocumentSegment]:
    text = content.decode("utf-8", errors="replace")
    headings = list(_HEADING_PATTERN.finditer(text))
    if not headings:
        return segment_plain_text(content)

    segments: list[DocumentSegment] = []
    heading_stack: list[tuple[int, str]] = []
    for index, match in enumerate(headings):
        level = len(match.group(1))
        title = match.group(2).strip()
        heading_stack = [h for h in heading_stack if h[0] < level] + [(level, title)]
        path = " > ".join(t for _, t in heading_stack)

        start = match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[start:end].strip()
        if body:
            segments.append(DocumentSegment(text=body, locator=ChunkLocator(kind="section", value=path)))
    return segments


def segment_plain_text(content: bytes) -> list[DocumentSegment]:
    lines = content.decode("utf-8", errors="replace").splitlines()
    segments: list[DocumentSegment] = []
    for start in range(0, len(lines), _LINE_RANGE_SIZE):
        chunk_lines = lines[start : start + _LINE_RANGE_SIZE]
        body = "\n".join(chunk_lines).strip()
        if body:
            first, last = start + 1, start + len(chunk_lines)
            segments.append(
                DocumentSegment(text=body, locator=ChunkLocator(kind="line_range", value=f"{first}-{last}"))
            )
    return segments
