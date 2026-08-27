"""Pydantic request/response models. Kept out of `application` on purpose —
the use case layer must not know it's being called over HTTP.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from bank_rag.domain.entities import Audience, NoIndexRuleType


class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=2000)


class CitationResponse(BaseModel):
    document_id: str
    title: str
    snippet: str
    score: float


class ChatResponse(BaseModel):
    conversation_id: UUID
    answer: str
    citations: list[CitationResponse]
    grounded: bool


class IngestResponse(BaseModel):
    source_id: str
    chunks_indexed: int


class IngestUrlRequest(BaseModel):
    url: str = Field(min_length=1, description="URL nel dominio consentito, es. https://www.example-bank.it/faq")
    title: str | None = Field(default=None, description="Se omesso, usa il <title> della pagina")
    audience: Audience = Audience.PUBLIC


class DocumentResponse(BaseModel):
    source_id: str
    title: str
    audience: Audience
    uploaded_by: str | None
    version: int
    updated_at: datetime


class NoIndexRuleRequest(BaseModel):
    pattern: str = Field(min_length=1, description="URL o source_id, con wildcard glob (es. '.../promo/*')")
    rule_type: NoIndexRuleType
    reason: str = Field(min_length=1, max_length=500)
    locator_kind: str | None = Field(
        default=None,
        description=(
            "Se impostato, limita l'esclusione a una porzione del documento invece che a tutto: "
            "'page' (PDF), 'section' (DOCX/MD/HTML), 'line_range' (TXT), 'row_range' (CSV/Excel), "
            "'json_path' (JSON), 'xpath' (XML)."
        ),
    )
    locator_pattern: str | None = Field(
        default=None, description="Wildcard glob sul valore del locator (es. '7' per pagina 7, 'Cookie*' per sezione)"
    )


class NoIndexRuleResponse(BaseModel):
    pattern: str
    rule_type: NoIndexRuleType
    reason: str
    created_by: str
    locator_kind: str | None
    locator_pattern: str | None
    created_at: datetime
