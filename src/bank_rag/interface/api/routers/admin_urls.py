"""Employee-only endpoint to ingest a single URL on demand — the UI-driven
counterpart to the scheduled crawl in ingestion/pipeline.py. An employee who
just published a new page doesn't need to wait for the next scheduled sync.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from bank_rag.application.use_cases.ingest_document import DocumentExcludedError
from bank_rag.di_container import get_settings
from bank_rag.ingestion.loaders.web_scraper import WebScraper
from bank_rag.interface.api.dependencies import (
    RequestIdentity,
    get_identity,
    get_ingest_document_use_case,
    rate_limit,
)
from bank_rag.interface.api.schemas import IngestResponse, IngestUrlRequest

router = APIRouter(prefix="/admin/urls", tags=["admin"])


@router.post(
    "",
    response_model=IngestResponse,
    dependencies=[Depends(rate_limit(get_settings().rate_limit_admin_per_minute, 60))],
)
async def ingest_url(
    request: IngestUrlRequest,
    identity: RequestIdentity = Depends(get_identity),
) -> IngestResponse:
    if not identity.is_employee:
        raise HTTPException(status_code=403, detail="employee authentication required")

    settings = get_settings()
    scraper = WebScraper(allowed_domain=settings.allowed_scrape_domain)
    try:
        page = await scraper.fetch(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    use_case = await get_ingest_document_use_case()
    try:
        chunks_indexed = await use_case.execute(
            source_id=request.url,
            title=request.title or page.title,
            segments=page.segments,
            audience=request.audience,
            uploaded_by=identity.customer_id or "unknown",
        )
    except DocumentExcludedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IngestResponse(source_id=request.url, chunks_indexed=chunks_indexed)
