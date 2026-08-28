"""Framework-agnostic domain model. No dependency on FastAPI, OpenAI, Qdrant, etc.

This module must never import from `infrastructure`, `interface` or any SDK.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4


class Audience(str, Enum):
    """Visibility scope of an indexed document. Enforced at retrieval time."""

    PUBLIC = "public"
    INTERNAL = "internal"


class Intent(str, Enum):
    ACCOUNT_BALANCE = "account_balance"
    PRODUCT_INFO = "product_info"
    PRODUCT_COMPARISON = "product_comparison"
    SMALLTALK = "smalltalk"
    HUMAN_HANDOFF = "human_handoff"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DocumentMetadata:
    source_id: str
    title: str
    audience: Audience
    uploaded_by: str | None
    version: int
    updated_at: datetime


@dataclass(frozen=True)
class ChunkLocator:
    """Addresses a specific position within a source document — a PDF page,
    a Markdown/DOCX/HTML heading section, a CSV/Excel row range, a JSON
    path, an XML element path, or 'whole' as a fallback when no finer
    structure was detected. This is the unit that granular no-index
    exclusion operates on (see NoIndexRule.locator_pattern).
    """

    kind: str  # "page" | "section" | "line_range" | "row_range" | "json_path" | "xpath" | "whole"
    value: str


_WHOLE_DOCUMENT_LOCATOR = ChunkLocator(kind="whole", value="document")


@dataclass(frozen=True)
class DocumentSegment:
    """A structurally-addressable slice of a source document, produced by a
    format-specific segmenter (see ingestion/segmentation/) before chunking.
    """

    text: str
    locator: ChunkLocator = _WHOLE_DOCUMENT_LOCATOR


@dataclass(frozen=True)
class Chunk:
    id: UUID
    document_id: str
    text: str
    metadata: DocumentMetadata
    locator: ChunkLocator = _WHOLE_DOCUMENT_LOCATOR
    embedding: list[float] | None = None


@dataclass(frozen=True)
class Citation:
    document_id: str
    title: str
    snippet: str
    score: float


@dataclass(frozen=True)
class ConversationTurn:
    role: str  # "user" | "assistant" | "tool"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class PendingAction:
    """A high-risk tool call the agent has proposed but not executed —
    the deterministic confirm path production banking-chatbot guidance
    calls for (see ARCHITECTURE.md). Lives on Conversation until the next
    customer message either confirms it (agent executes tool_name with
    arguments) or doesn't (it's discarded, nothing runs).
    """

    tool_name: str
    arguments: dict[str, object]
    confirmation_prompt: str


@dataclass
class Conversation:
    id: UUID = field(default_factory=uuid4)
    customer_id: str | None = None
    is_authenticated: bool = False
    turns: list[ConversationTurn] = field(default_factory=list)
    pending_action: PendingAction | None = None

    def add(self, turn: ConversationTurn) -> None:
        self.turns.append(turn)

    def history_as_messages(self, max_turns: int = 12) -> list[dict[str, str]]:
        return [{"role": t.role, "content": t.content} for t in self.turns[-max_turns:]]


@dataclass(frozen=True)
class Answer:
    text: str
    citations: list[Citation]
    intent: Intent
    grounded: bool
    pending_action: PendingAction | None = None


class NoIndexRuleType(str, Enum):
    URL = "url"
    SOURCE_ID = "source_id"


@dataclass(frozen=True)
class NoIndexRule:
    """Excludes a URL or source_id (glob pattern, e.g. '.../promo/*') from
    ingestion. Adding a rule also purges any already-indexed content that
    matches it — see ManageNoIndexRules.

    When locator_kind/locator_pattern are set, the exclusion is scoped to
    segments whose ChunkLocator matches (e.g. locator_kind="page",
    locator_pattern="7" excludes only page 7 of a PDF; locator_kind=
    "section", locator_pattern="Promozioni*" excludes matching sections of a
    DOCX/MD/HTML page). Left as None, the rule excludes the whole document —
    unchanged behavior from before granular exclusion existed.
    """

    pattern: str
    rule_type: NoIndexRuleType
    reason: str
    created_by: str
    locator_kind: str | None = None
    locator_pattern: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class AuditEntry:
    """One immutable record of a chat exchange, for regulatory traceability —
    distinct from OpenTelemetry tracing (observability/tracing.py), which is
    for engineering diagnostics and is not held to the same retention/
    non-repudiation requirements as a compliance audit trail.
    """

    id: UUID
    conversation_id: UUID
    customer_id: str | None
    question: str
    resolved_question: str
    retrieved_document_ids: list[str]
    answer_text: str
    intent: Intent
    grounded: bool
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
