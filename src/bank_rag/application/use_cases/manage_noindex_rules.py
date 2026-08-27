"""Use case: ManageNoIndexRules.

Supports two granularities:
- Whole-document (locator_kind/locator_pattern left None): matches the pre-
  existing behavior — purges entire matching documents from both indexes.
- Segment-scoped (locator_kind + locator_pattern set): purges only chunks
  whose locator matches, via VectorStore/KeywordIndex.delete_by_locator —
  the rest of the document stays indexed and searchable.
"""
from __future__ import annotations

from fnmatch import fnmatch

from bank_rag.application.ports.document_repository import DocumentRepository
from bank_rag.application.ports.keyword_index import KeywordIndex
from bank_rag.application.ports.noindex_registry import NoIndexRegistry
from bank_rag.application.ports.vector_store import VectorStore
from bank_rag.domain.entities import NoIndexRule, NoIndexRuleType


class ManageNoIndexRules:
    def __init__(
        self,
        registry: NoIndexRegistry,
        vector_store: VectorStore,
        keyword_index: KeywordIndex,
        document_repository: DocumentRepository,
    ) -> None:
        self._registry = registry
        self._vector_store = vector_store
        self._keyword_index = keyword_index
        self._documents = document_repository

    async def exclude(
        self,
        pattern: str,
        rule_type: NoIndexRuleType,
        reason: str,
        created_by: str,
        locator_kind: str | None = None,
        locator_pattern: str | None = None,
    ) -> int:
        """Adds the rule and immediately purges matching already-indexed
        content. Returns the number of chunks purged when scoped by locator,
        or the number of whole documents purged otherwise.
        """
        await self._registry.add_rule(
            NoIndexRule(
                pattern=pattern, rule_type=rule_type, reason=reason, created_by=created_by,
                locator_kind=locator_kind, locator_pattern=locator_pattern,
            )
        )

        purged = 0
        for doc in await self._documents.list_all():
            if not fnmatch(doc.source_id, pattern):
                continue
            if locator_kind and locator_pattern:
                purged += await self._vector_store.delete_by_locator(doc.source_id, locator_kind, locator_pattern)
                await self._keyword_index.delete_by_locator(doc.source_id, locator_kind, locator_pattern)
            else:
                await self._vector_store.delete_by_document(doc.source_id)
                await self._keyword_index.delete_by_document(doc.source_id)
                purged += 1
        return purged

    async def include(self, pattern: str) -> None:
        """Removes a rule. Does NOT re-index anything — a future crawl/upload
        of matching content will simply no longer be blocked.
        """
        await self._registry.remove_rule(pattern)

    async def list_rules(self) -> list[NoIndexRule]:
        return await self._registry.list_rules()
