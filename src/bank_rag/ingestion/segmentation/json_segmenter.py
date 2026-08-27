"""Segments JSON at the top level: one segment per key (object root) or per
item (array root). Nested structure within a segment stays intact — only
the top-level boundary is addressable by a no-index rule, matching how a
bank typically organizes exported structured data (a product catalog, a
rate table) by top-level entries.
"""
from __future__ import annotations

import json

from bank_rag.domain.entities import ChunkLocator, DocumentSegment


def segment_json(content: bytes) -> list[DocumentSegment]:
    data = json.loads(content.decode("utf-8"))
    segments: list[DocumentSegment] = []

    if isinstance(data, dict):
        for key, value in data.items():
            text = json.dumps({key: value}, ensure_ascii=False, indent=2)
            segments.append(DocumentSegment(text=text, locator=ChunkLocator(kind="json_path", value=f"$.{key}")))
    elif isinstance(data, list):
        for index, item in enumerate(data):
            text = json.dumps(item, ensure_ascii=False, indent=2)
            segments.append(DocumentSegment(text=text, locator=ChunkLocator(kind="json_path", value=f"$[{index}]")))
    else:
        text = json.dumps(data, ensure_ascii=False)
        segments.append(DocumentSegment(text=text, locator=ChunkLocator(kind="json_path", value="$")))

    return segments
