"""Internal source: files uploaded by bank employees through the admin panel.

Dispatches to a per-format segmenter (see ingestion/segmentation/) instead of
flattening straight to text — this is what lets a no-index rule exclude a
specific page/section/row-range of a file, not only ever the whole thing.
"""
from __future__ import annotations

from collections.abc import Callable

from bank_rag.domain.entities import DocumentSegment
from bank_rag.ingestion.segmentation.csv_segmenter import segment_csv
from bank_rag.ingestion.segmentation.docx_segmenter import segment_docx
from bank_rag.ingestion.segmentation.json_segmenter import segment_json
from bank_rag.ingestion.segmentation.markdown_segmenter import segment_markdown, segment_plain_text
from bank_rag.ingestion.segmentation.pdf_segmenter import segment_pdf
from bank_rag.ingestion.segmentation.xlsx_segmenter import segment_xlsx
from bank_rag.ingestion.segmentation.xml_segmenter import segment_xml

_SEGMENTERS: dict[str, Callable[[bytes], list[DocumentSegment]]] = {
    "pdf": segment_pdf,
    "docx": segment_docx,
    "md": segment_markdown,
    "markdown": segment_markdown,
    "txt": segment_plain_text,
    "csv": segment_csv,
    "xlsx": segment_xlsx,
    "xlsm": segment_xlsx,
    "json": segment_json,
    "xml": segment_xml,
}


class UnsupportedFileTypeError(Exception):
    pass


class FileLoader:
    def load(self, filename: str, content: bytes) -> list[DocumentSegment]:
        extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        segmenter = _SEGMENTERS.get(extension)
        if segmenter is None:
            raise UnsupportedFileTypeError(
                f"unsupported file type: {filename} (supported: {', '.join(sorted(_SEGMENTERS))})"
            )
        return segmenter(content)
