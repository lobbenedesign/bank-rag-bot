from __future__ import annotations

from datetime import UTC, datetime
from fnmatch import fnmatch

import pytest

from bank_rag.application.use_cases.manage_noindex_rules import ManageNoIndexRules
from bank_rag.domain.entities import Audience, ChunkLocator, DocumentMetadata, NoIndexRule, NoIndexRuleType


class InMemoryRegistry:
    def __init__(self) -> None:
        self._rules: dict[str, NoIndexRule] = {}

    async def add_rule(self, rule: NoIndexRule) -> None:
        self._rules[rule.pattern] = rule

    async def remove_rule(self, pattern: str) -> None:
        self._rules.pop(pattern, None)

    async def list_rules(self) -> list[NoIndexRule]:
        return list(self._rules.values())

    async def is_excluded(self, identifier: str, locator: ChunkLocator | None = None) -> bool:
        for rule in self._rules.values():
            if not fnmatch(identifier, rule.pattern):
                continue
            if rule.locator_kind is None:
                return True
            if locator is not None and locator.kind == rule.locator_kind and fnmatch(
                locator.value, rule.locator_pattern or "*"
            ):
                return True
        return False


class InMemoryIndex:
    def __init__(self) -> None:
        self.deleted_document_ids: list[str] = []
        # (document_id, locator_kind, locator_value) tuples still "indexed"
        self.chunk_locators: list[tuple[str, str, str]] = []

    async def delete_by_document(self, document_id: str) -> None:
        self.deleted_document_ids.append(document_id)
        self.chunk_locators = [c for c in self.chunk_locators if c[0] != document_id]

    async def delete_by_locator(self, document_id: str, locator_kind: str, locator_pattern: str) -> int:
        before = len(self.chunk_locators)
        self.chunk_locators = [
            c for c in self.chunk_locators
            if not (c[0] == document_id and c[1] == locator_kind and fnmatch(c[2], locator_pattern))
        ]
        return before - len(self.chunk_locators)


class InMemoryDocumentRepository:
    def __init__(self, documents: list[DocumentMetadata]) -> None:
        self._documents = documents

    async def list_all(self) -> list[DocumentMetadata]:
        return self._documents

    async def save_metadata(self, metadata):
        raise NotImplementedError

    async def get_latest_version(self, source_id):
        raise NotImplementedError

    async def list_by_audience(self, audience):
        raise NotImplementedError


def _doc(source_id: str) -> DocumentMetadata:
    return DocumentMetadata(
        source_id=source_id, title=source_id, audience=Audience.PUBLIC,
        uploaded_by="employee-1", version=1, updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_excluding_a_url_pattern_purges_matching_already_indexed_pages():
    vector_store = InMemoryIndex()
    keyword_index = InMemoryIndex()
    documents = InMemoryDocumentRepository(
        [
            _doc("https://www.example-bank.it/promo/estate-2026"),
            _doc("https://www.example-bank.it/promo/inverno-2026"),
            _doc("https://www.example-bank.it/faq"),
        ]
    )
    use_case = ManageNoIndexRules(InMemoryRegistry(), vector_store, keyword_index, documents)

    purged = await use_case.exclude(
        pattern="https://www.example-bank.it/promo/*",
        rule_type=NoIndexRuleType.URL,
        reason="promozione scaduta",
        created_by="employee-1",
    )

    assert purged == 2
    assert set(vector_store.deleted_document_ids) == {
        "https://www.example-bank.it/promo/estate-2026",
        "https://www.example-bank.it/promo/inverno-2026",
    }
    assert set(keyword_index.deleted_document_ids) == set(vector_store.deleted_document_ids)


@pytest.mark.asyncio
async def test_excluding_a_page_purges_only_matching_chunks_not_the_whole_document():
    vector_store = InMemoryIndex()
    vector_store.chunk_locators = [
        ("foglio_informativo.pdf", "page", "1"),
        ("foglio_informativo.pdf", "page", "2"),
        ("foglio_informativo.pdf", "page", "3"),
    ]
    keyword_index = InMemoryIndex()
    keyword_index.chunk_locators = list(vector_store.chunk_locators)
    documents = InMemoryDocumentRepository([_doc("foglio_informativo.pdf")])
    use_case = ManageNoIndexRules(InMemoryRegistry(), vector_store, keyword_index, documents)

    purged = await use_case.exclude(
        pattern="foglio_informativo.pdf",
        rule_type=NoIndexRuleType.SOURCE_ID,
        reason="pagina 2 contiene condizioni superate",
        created_by="employee-1",
        locator_kind="page",
        locator_pattern="2",
    )

    assert purged == 1
    assert vector_store.deleted_document_ids == []  # whole-document delete never called
    remaining_pages = {locator for _, _, locator in vector_store.chunk_locators}
    assert remaining_pages == {"1", "3"}


@pytest.mark.asyncio
async def test_rule_blocks_future_ingestion_of_matching_identifier():
    registry = InMemoryRegistry()
    use_case = ManageNoIndexRules(registry, InMemoryIndex(), InMemoryIndex(), InMemoryDocumentRepository([]))

    await use_case.exclude("condizioni_riservate_vip.pdf", NoIndexRuleType.SOURCE_ID, "solo per staff interno", "employee-1")

    assert await registry.is_excluded("condizioni_riservate_vip.pdf") is True
    assert await registry.is_excluded("faq_pubbliche.pdf") is False


@pytest.mark.asyncio
async def test_locator_scoped_rule_only_excludes_matching_locator():
    registry = InMemoryRegistry()
    use_case = ManageNoIndexRules(registry, InMemoryIndex(), InMemoryIndex(), InMemoryDocumentRepository([]))

    await use_case.exclude(
        "foglio_informativo.pdf", NoIndexRuleType.SOURCE_ID, "condizioni superate", "employee-1",
        locator_kind="page", locator_pattern="2",
    )

    assert await registry.is_excluded("foglio_informativo.pdf") is False  # no locator -> whole-doc check, not excluded
    assert await registry.is_excluded("foglio_informativo.pdf", ChunkLocator(kind="page", value="2")) is True
    assert await registry.is_excluded("foglio_informativo.pdf", ChunkLocator(kind="page", value="1")) is False


@pytest.mark.asyncio
async def test_include_removes_the_rule():
    registry = InMemoryRegistry()
    use_case = ManageNoIndexRules(registry, InMemoryIndex(), InMemoryIndex(), InMemoryDocumentRepository([]))
    await use_case.exclude("old_promo.pdf", NoIndexRuleType.SOURCE_ID, "test", "employee-1")

    await use_case.include("old_promo.pdf")

    assert await registry.is_excluded("old_promo.pdf") is False
