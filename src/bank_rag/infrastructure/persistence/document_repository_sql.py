"""SQL-backed system of record for document metadata (via SQLAlchemy async engine).

Table DDL lives in `alembic` migrations (not shown here) — this adapter only
talks in terms of the domain's DocumentMetadata, never leaking ORM models
upward into the application layer.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from bank_rag.domain.entities import Audience, DocumentMetadata


class Base(DeclarativeBase):
    pass


class DocumentMetadataRow(Base):
    __tablename__ = "document_metadata"

    source_id: str = Column(String, primary_key=True)
    title: str = Column(String, nullable=False)
    audience: str = Column(String, nullable=False)
    uploaded_by: str | None = Column(String, nullable=True)
    version: int = Column(Integer, nullable=False)
    updated_at: datetime = Column(DateTime(timezone=True), nullable=False)


class SqlDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_metadata(self, metadata: DocumentMetadata) -> None:
        row = await self._session.get(DocumentMetadataRow, metadata.source_id)
        if row is None:
            row = DocumentMetadataRow(source_id=metadata.source_id)
            self._session.add(row)
        row.title = metadata.title
        row.audience = metadata.audience.value
        row.uploaded_by = metadata.uploaded_by
        row.version = metadata.version
        row.updated_at = metadata.updated_at
        await self._session.commit()

    async def get_latest_version(self, source_id: str) -> int:
        row = await self._session.get(DocumentMetadataRow, source_id)
        return row.version if row else 0

    async def list_by_audience(self, audience: str) -> list[DocumentMetadata]:
        result = await self._session.execute(
            select(DocumentMetadataRow).where(DocumentMetadataRow.audience == audience)
        )
        return [self._to_metadata(r) for r in result.scalars()]

    async def list_all(self) -> list[DocumentMetadata]:
        result = await self._session.execute(select(DocumentMetadataRow))
        return [self._to_metadata(r) for r in result.scalars()]

    @staticmethod
    def _to_metadata(r: DocumentMetadataRow) -> DocumentMetadata:
        return DocumentMetadata(
            source_id=r.source_id,
            title=r.title,
            audience=Audience(r.audience),
            uploaded_by=r.uploaded_by,
            version=r.version,
            updated_at=r.updated_at or datetime.now(UTC),
        )
