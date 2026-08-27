"""Stores no-index rules (Postgres) and matches identifiers/locators against
them with glob semantics (fnmatch), so a single rule like
'https://www.example-bank.it/promo/*' excludes a whole URL subtree, and a
locator-scoped rule like (pattern='report_tassi.xlsx', locator_kind=
'row_range', locator_pattern='Tassi!*') excludes only matching rows of one
sheet in one file.
"""
from __future__ import annotations

from datetime import datetime
from fnmatch import fnmatch

from sqlalchemy import Column, DateTime, String, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_rag.domain.entities import ChunkLocator, NoIndexRule, NoIndexRuleType
from bank_rag.infrastructure.persistence.document_repository_sql import Base


class NoIndexRuleRow(Base):
    __tablename__ = "noindex_rules"

    pattern: str = Column(String, primary_key=True)
    rule_type: str = Column(String, nullable=False)
    reason: str = Column(String, nullable=False)
    created_by: str = Column(String, nullable=False)
    locator_kind: str | None = Column(String, nullable=True)
    locator_pattern: str | None = Column(String, nullable=True)
    created_at: datetime = Column(DateTime(timezone=True), nullable=False)


class SqlNoIndexRegistry:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_rule(self, rule: NoIndexRule) -> None:
        row = await self._session.get(NoIndexRuleRow, rule.pattern)
        if row is None:
            row = NoIndexRuleRow(pattern=rule.pattern)
            self._session.add(row)
        row.rule_type = rule.rule_type.value
        row.reason = rule.reason
        row.created_by = rule.created_by
        row.locator_kind = rule.locator_kind
        row.locator_pattern = rule.locator_pattern
        row.created_at = rule.created_at
        await self._session.commit()

    async def remove_rule(self, pattern: str) -> None:
        await self._session.execute(delete(NoIndexRuleRow).where(NoIndexRuleRow.pattern == pattern))
        await self._session.commit()

    async def list_rules(self) -> list[NoIndexRule]:
        result = await self._session.execute(select(NoIndexRuleRow))
        return [
            NoIndexRule(
                pattern=r.pattern,
                rule_type=NoIndexRuleType(r.rule_type),
                reason=r.reason,
                created_by=r.created_by,
                locator_kind=r.locator_kind,
                locator_pattern=r.locator_pattern,
                created_at=r.created_at,
            )
            for r in result.scalars()
        ]

    async def is_excluded(self, identifier: str, locator: ChunkLocator | None = None) -> bool:
        for rule in await self.list_rules():
            if not fnmatch(identifier, rule.pattern):
                continue
            if rule.locator_kind is None:
                return True  # whole-document rule
            if locator is not None and locator.kind == rule.locator_kind and fnmatch(
                locator.value, rule.locator_pattern or "*"
            ):
                return True
        return False
