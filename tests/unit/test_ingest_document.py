from __future__ import annotations

import pytest

from bank_rag.application.use_cases.ingest_document import DocumentExcludedError, IngestDocument
from bank_rag.domain.entities import Audience, ChunkLocator, DocumentSegment
from bank_rag.ingestion.chunking.semantic_chunker import SemanticChunker


class FakeEmbedder:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.0]


class FakeIndex:
    def __init__(self) -> None:
        self.upserted: list = []
        self.deleted_document_ids: list[str] = []

    async def upsert(self, chunks) -> None:
        self.upserted.extend(chunks)

    async def index(self, chunks) -> None:
        self.upserted.extend(chunks)

    async def delete_by_document(self, document_id: str) -> None:
        self.deleted_document_ids.append(document_id)

    async def delete_by_locator(self, document_id: str, locator_kind: str, locator_pattern: str) -> int:
        return 0


class FakeDocumentRepository:
    def __init__(self) -> None:
        self._versions: dict[str, int] = {}
        self.saved: list = []

    async def save_metadata(self, metadata) -> None:
        self._versions[metadata.source_id] = metadata.version
        self.saved.append(metadata)

    async def get_latest_version(self, source_id: str) -> int:
        return self._versions.get(source_id, 0)

    async def list_by_audience(self, audience):
        raise NotImplementedError

    async def list_all(self):
        raise NotImplementedError


class PassthroughSanitizer:
    def sanitize(self, text: str) -> str:
        return text


class AlwaysExcludedRegistry:
    async def is_excluded(self, identifier: str, locator=None) -> bool:
        return True


class NeverExcludedRegistry:
    async def is_excluded(self, identifier: str, locator=None) -> bool:
        return False


class ExcludesOnePageRegistry:
    """Whole-document allowed, but page '2' specifically excluded."""

    async def is_excluded(self, identifier: str, locator=None) -> bool:
        return locator is not None and locator.kind == "page" and locator.value == "2"


def _use_case(noindex_registry) -> IngestDocument:
    return IngestDocument(
        SemanticChunker(), FakeEmbedder(), FakeIndex(), FakeIndex(),
        FakeDocumentRepository(), PassthroughSanitizer(), noindex_registry,
    )


@pytest.mark.asyncio
async def test_refuses_to_ingest_a_source_id_matching_a_noindex_rule():
    use_case = _use_case(AlwaysExcludedRegistry())
    with pytest.raises(DocumentExcludedError):
        await use_case.execute(
            source_id="condizioni_riservate_vip.pdf", title="VIP",
            segments=[DocumentSegment(text="testo", locator=ChunkLocator(kind="whole", value="document"))],
            audience=Audience.INTERNAL, uploaded_by="employee-1",
        )


@pytest.mark.asyncio
async def test_ingests_normally_when_not_excluded():
    use_case = _use_case(NeverExcludedRegistry())
    chunks_indexed = await use_case.execute(
        source_id="faq_pubbliche.pdf", title="FAQ",
        segments=[DocumentSegment(text="Il Conto Base non ha canone.", locator=ChunkLocator(kind="whole", value="document"))],
        audience=Audience.PUBLIC, uploaded_by="employee-1",
    )
    assert chunks_indexed == 1


@pytest.mark.asyncio
async def test_excludes_only_the_matching_segment_keeping_the_rest():
    use_case = _use_case(ExcludesOnePageRegistry())
    segments = [
        DocumentSegment(text="Contenuto pagina 1.", locator=ChunkLocator(kind="page", value="1")),
        DocumentSegment(text="Contenuto riservato pagina 2.", locator=ChunkLocator(kind="page", value="2")),
        DocumentSegment(text="Contenuto pagina 3.", locator=ChunkLocator(kind="page", value="3")),
    ]

    chunks_indexed = await use_case.execute(
        source_id="foglio_informativo.pdf", title="Foglio informativo",
        segments=segments, audience=Audience.PUBLIC, uploaded_by="employee-1",
    )

    # Page 2 excluded, pages 1 and 3 still indexed — not an all-or-nothing outcome.
    assert chunks_indexed == 2
