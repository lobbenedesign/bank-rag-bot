"""Segments CSV into fixed-size row batches, each carrying the header row as
context so a batch stays intelligible on its own. Locator value is a 1-indexed
row range counting the header as row 1 — matches how a bank employee would
actually reference "rows 12-30" when looking at the file in a spreadsheet app.
"""
from __future__ import annotations

import csv
import io

from bank_rag.domain.entities import ChunkLocator, DocumentSegment

_ROWS_PER_SEGMENT = 50


def segment_csv(content: bytes) -> list[DocumentSegment]:
    text = content.decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []

    header, data_rows = rows[0], rows[1:]
    segments: list[DocumentSegment] = []
    for start in range(0, len(data_rows), _ROWS_PER_SEGMENT):
        batch = data_rows[start : start + _ROWS_PER_SEGMENT]
        lines = [", ".join(header)] + [", ".join(row) for row in batch]
        first, last = start + 2, start + 1 + len(batch)  # +2: header occupies row 1
        segments.append(
            DocumentSegment(text="\n".join(lines), locator=ChunkLocator(kind="row_range", value=f"{first}-{last}"))
        )
    return segments
