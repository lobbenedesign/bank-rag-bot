"""Segments a PDF into paragraphs, addressed as "page:paragraph" (e.g. "7:3").

Uses pdfplumber, not pypdf: pypdf exposes only page-level text extraction
(no line/word coordinates), so paragraph boundaries were previously
undetectable and the whole page was the smallest addressable unit. pdfplumber
exposes per-line bounding boxes, which lets us detect paragraph breaks as
unusually large vertical gaps between consecutive lines — the same heuristic
a human uses when skimming a page.

Library choice, stated explicitly: PyMuPDF (fitz) also does this, often with
higher out-of-the-box accuracy on complex layouts, but is AGPL-3.0 (or
requires a paid commercial license from Artifex for closed-source use) —
unacceptable for embedding into a bank's proprietary backend without either
open-sourcing this codebase or buying a commercial license. pdfplumber
(MIT, built on pdfminer.six) has no such constraint. This is a licensing
decision, not just a technical one, and it belongs in a banking codebase's
paper trail as much as any security control does.

Tables (rate sheets are almost always a table of duration x rate): the
paragraph-gap heuristic above reads a table left-to-right, top-to-bottom
as if it were prose, which silently destroys the row/column alignment
between e.g. "30 years" and "3.50%" — exactly the failure mode that matters
most for a banking document. `page.find_tables()` (pdfplumber's own
line/rect-based table detector) locates each table's bounding box; its
cells are rendered as a real Markdown table (an LLM reads Markdown table
structure correctly, unlike flattened prose) and emitted as its own
DocumentSegment/chunk. Text lines that fall inside a detected table's
bounding box are then excluded from the paragraph grouping below, so the
table's content is never duplicated (once correctly, as Markdown; a second
time, garbled, as a "paragraph"). Honest limitation: detection needs
visible ruling lines/borders in the PDF — a table with no drawn grid
(spacing-only alignment) is not detected and falls through to the
paragraph path like before this change, unchanged behavior.
"""
from __future__ import annotations

import io
import statistics

import pdfplumber

from bank_rag.domain.entities import ChunkLocator, DocumentSegment

# A gap this many times the page's median line height is treated as a
# paragraph break rather than an ordinary line break within one paragraph.
_PARAGRAPH_GAP_MULTIPLIER = 1.6
_DEFAULT_LINE_HEIGHT = 12.0


def segment_pdf(content: bytes) -> list[DocumentSegment]:
    segments: list[DocumentSegment] = []

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            tables = page.find_tables()
            for table_index, table in enumerate(tables, start=1):
                markdown = _table_to_markdown(table.extract())
                if markdown:
                    locator = ChunkLocator(kind="page_table", value=f"{page_index}:{table_index}")
                    segments.append(DocumentSegment(text=markdown, locator=locator))

            table_bboxes = [t.bbox for t in tables]
            lines = page.extract_text_lines(layout=False) or []
            lines = [line for line in lines if not _line_inside_any(line, table_bboxes)]
            for paragraph_index, paragraph_text in enumerate(_group_into_paragraphs(lines), start=1):
                if paragraph_text:
                    locator = ChunkLocator(kind="page_paragraph", value=f"{page_index}:{paragraph_index}")
                    segments.append(DocumentSegment(text=paragraph_text, locator=locator))

    return segments


def _table_to_markdown(rows: list[list[str | None]]) -> str:
    """Real GitHub-flavored Markdown table — the format LLMs reliably parse
    back into rows/columns, unlike a flattened space-joined string."""
    clean_rows = [[(cell or "").strip().replace("\n", " ") for cell in row] for row in rows if any(row)]
    if not clean_rows:
        return ""
    header, *body = clean_rows
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *("| " + " | ".join(row) + " |" for row in body),
    ]
    return "\n".join(lines)


def _line_inside_any(line: dict, bboxes: list[tuple[float, float, float, float]]) -> bool:
    # Midpoint containment, not strict full-overlap: a text line's bbox can
    # extend a point or two past a table's detected border due to rendering
    # rounding, which a strict "fully inside" check would miss entirely.
    mid_y = (line["top"] + line["bottom"]) / 2
    mid_x = (line["x0"] + line["x1"]) / 2
    return any(x0 <= mid_x <= x1 and top <= mid_y <= bottom for x0, top, x1, bottom in bboxes)


def _group_into_paragraphs(lines: list[dict]) -> list[str]:
    if not lines:
        return []

    heights = [line["bottom"] - line["top"] for line in lines if line["bottom"] > line["top"]]
    median_height = statistics.median(heights) if heights else _DEFAULT_LINE_HEIGHT
    gap_threshold = median_height * _PARAGRAPH_GAP_MULTIPLIER

    paragraphs: list[list[str]] = [[]]
    previous_bottom: float | None = None

    for line in lines:
        text = (line.get("text") or "").strip()
        if not text:
            continue
        if previous_bottom is not None and (line["top"] - previous_bottom) > gap_threshold:
            paragraphs.append([])
        paragraphs[-1].append(text)
        previous_bottom = line["bottom"]

    return [" ".join(p).strip() for p in paragraphs if p]
