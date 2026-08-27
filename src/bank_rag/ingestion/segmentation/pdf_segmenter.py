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
            lines = page.extract_text_lines(layout=False) or []
            for paragraph_index, paragraph_text in enumerate(_group_into_paragraphs(lines), start=1):
                if paragraph_text:
                    locator = ChunkLocator(kind="page_paragraph", value=f"{page_index}:{paragraph_index}")
                    segments.append(DocumentSegment(text=paragraph_text, locator=locator))

    return segments


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
