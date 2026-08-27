"""Employee-only endpoint to upload documents into the knowledge base.

`identity.is_employee` gate is deliberately checked here at the transport
edge — a customer-facing token can never reach IngestDocument.execute.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from bank_rag.application.use_cases.ingest_document import DocumentExcludedError
from bank_rag.di_container import build_document_repository, get_settings
from bank_rag.domain.entities import Audience
from bank_rag.interface.api.dependencies import (
    RequestIdentity,
    get_identity,
    get_ingest_document_use_case,
    rate_limit,
)
from bank_rag.interface.api.schemas import DocumentResponse, IngestResponse
from bank_rag.ingestion.loaders.file_loader import FileLoader, UnsupportedFileTypeError

router = APIRouter(prefix="/admin/documents", tags=["admin"])
_file_loader = FileLoader()


@router.post(
    "",
    response_model=IngestResponse,
    dependencies=[Depends(rate_limit(get_settings().rate_limit_admin_per_minute, 60))],
)
async def upload_document(
    title: str = Form(...),
    audience: Audience = Form(default=Audience.INTERNAL),
    file: UploadFile = File(...),
    identity: RequestIdentity = Depends(get_identity),
) -> IngestResponse:
    if not identity.is_employee:
        raise HTTPException(status_code=403, detail="employee authentication required")

    content = await file.read()
    try:
        segments = _file_loader.load(file.filename or "", content)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    use_case = await get_ingest_document_use_case()
    try:
        chunks_indexed = await use_case.execute(
            source_id=file.filename or title,
            title=title,
            segments=segments,
            audience=audience,
            uploaded_by=identity.customer_id or "unknown",
        )
    except DocumentExcludedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IngestResponse(source_id=file.filename or title, chunks_indexed=chunks_indexed)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(identity: RequestIdentity = Depends(get_identity)) -> list[DocumentResponse]:
    if not identity.is_employee:
        raise HTTPException(status_code=403, detail="employee authentication required")

    documents = await build_document_repository().list_all()
    return [
        DocumentResponse(
            source_id=d.source_id, title=d.title, audience=d.audience,
            uploaded_by=d.uploaded_by, version=d.version, updated_at=d.updated_at,
        )
        for d in sorted(documents, key=lambda d: d.updated_at, reverse=True)
    ]
