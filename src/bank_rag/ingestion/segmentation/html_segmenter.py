"""Segments an HTML page by heading (h1-h3) into sections, mirroring
markdown_segmenter's approach — lets a no-index rule exclude one section of
a public page (e.g. an expired promo box on /privacy) without excluding the
whole URL.

Simplification, stated plainly: sections are built from each heading's
following flat siblings only, not full nested subtree traversal — correct
for typical simple content markup, not guaranteed for deeply nested layout
wrappers. A page that doesn't parse into any heading falls back to one
"whole" segment, same as before granular exclusion existed.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from bank_rag.domain.entities import ChunkLocator, DocumentSegment

_HEADING_TAGS = ("h1", "h2", "h3")


def segment_html(soup: BeautifulSoup) -> list[DocumentSegment]:
    headings = soup.find_all(_HEADING_TAGS)
    if not headings:
        text = " ".join(soup.get_text(separator=" ").split())
        return [DocumentSegment(text=text, locator=ChunkLocator(kind="whole", value="page"))] if text else []

    segments: list[DocumentSegment] = []
    heading_stack: list[tuple[int, str]] = []
    for heading in headings:
        level = int(heading.name[1])
        title = heading.get_text(strip=True)
        heading_stack = [h for h in heading_stack if h[0] < level] + [(level, title)]
        path = " > ".join(t for _, t in heading_stack)

        body_parts = []
        for sibling in heading.find_next_siblings():
            if sibling.name in _HEADING_TAGS:
                break
            body_parts.append(sibling.get_text(separator=" ", strip=True))
        body = " ".join(part for part in body_parts if part).strip()
        if body:
            segments.append(DocumentSegment(text=body, locator=ChunkLocator(kind="section", value=path)))
    return segments
