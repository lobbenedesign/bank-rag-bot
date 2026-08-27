"""Segments XML at the root's direct children — locator value is an
XPath-like '/root/item[3]' addressing the Nth child with that tag name,
letting a no-index rule exclude one entry of an XML feed/export.

Parses with defusedxml, not the stdlib xml.etree directly — an uploaded XML
file is still user-supplied content (an employee's mistake or a compromised
account), and stdlib XML parsing is vulnerable to entity-expansion attacks
(billion laughs) and XXE. defusedxml disables external entities and caps
expansion, at the same API surface.
"""
from __future__ import annotations

from xml.etree import ElementTree as _ElementTreeForSerialization

from defusedxml import ElementTree

from bank_rag.domain.entities import ChunkLocator, DocumentSegment


def segment_xml(content: bytes) -> list[DocumentSegment]:
    root = ElementTree.fromstring(content)
    segments: list[DocumentSegment] = []
    tag_counts: dict[str, int] = {}

    for child in root:
        tag_counts[child.tag] = tag_counts.get(child.tag, 0) + 1
        index = tag_counts[child.tag]
        text = (_ElementTreeForSerialization.tostring(child, encoding="unicode", method="text") or "").strip()
        if text:
            path = f"/{root.tag}/{child.tag}[{index}]"
            segments.append(DocumentSegment(text=text, locator=ChunkLocator(kind="xpath", value=path)))

    return segments
