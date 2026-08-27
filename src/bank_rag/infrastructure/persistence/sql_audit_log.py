"""Append-only compliance audit trail (Postgres via SQLAlchemy).

Append-only is enforced at two levels: (1) this class and the AuditLog port
it implements expose only `record`, never update/delete; (2) in production,
the database role this service connects as should additionally have UPDATE
and DELETE revoked on the `audit_log` table at the grant level — application
code discipline alone is not a substitute for a DB-enforced guarantee.
"""
from __future__ import annotations

import json

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.ext.asyncio import AsyncSession

from bank_rag.domain.entities import AuditEntry, Intent
from bank_rag.infrastructure.persistence.document_repository_sql import Base


class AuditLogRow(Base):
    __tablename__ = "audit_log"

    id: str = Column(String, primary_key=True)
    conversation_id: str = Column(String, nullable=False, index=True)
    customer_id: str | None = Column(String, nullable=True, index=True)
    question: str = Column(Text, nullable=False)
    resolved_question: str = Column(Text, nullable=False)
    retrieved_document_ids: str = Column(Text, nullable=False)  # JSON-encoded list[str]
    answer_text: str = Column(Text, nullable=False)
    intent: str = Column(String, nullable=False)
    grounded: bool = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class SqlAuditLog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, entry: AuditEntry) -> None:
        self._session.add(
            AuditLogRow(
                id=str(entry.id),
                conversation_id=str(entry.conversation_id),
                customer_id=entry.customer_id,
                question=entry.question,
                resolved_question=entry.resolved_question,
                retrieved_document_ids=json.dumps(entry.retrieved_document_ids),
                answer_text=entry.answer_text,
                intent=entry.intent.value if isinstance(entry.intent, Intent) else entry.intent,
                grounded=entry.grounded,
                created_at=entry.created_at,
            )
        )
        await self._session.commit()
