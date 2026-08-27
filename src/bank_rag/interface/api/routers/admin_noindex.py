"""Employee-only endpoints to exclude URLs/documents from ingestion.

Adding a rule purges any already-indexed content matching it immediately
(see ManageNoIndexRules) — this is not just a future-ingestion filter, it's
also a takedown mechanism for content that should never have been indexed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from bank_rag.di_container import build_manage_noindex_rules_use_case
from bank_rag.interface.api.dependencies import RequestIdentity, get_identity
from bank_rag.interface.api.schemas import NoIndexRuleRequest, NoIndexRuleResponse

router = APIRouter(prefix="/admin/noindex", tags=["admin"])


def _require_employee(identity: RequestIdentity) -> None:
    if not identity.is_employee:
        raise HTTPException(status_code=403, detail="employee authentication required")


@router.post("", response_model=dict)
async def exclude(
    request: NoIndexRuleRequest,
    identity: RequestIdentity = Depends(get_identity),
) -> dict:
    _require_employee(identity)
    use_case = build_manage_noindex_rules_use_case()
    purged = await use_case.exclude(
        pattern=request.pattern,
        rule_type=request.rule_type,
        reason=request.reason,
        created_by=identity.customer_id or "unknown",
        locator_kind=request.locator_kind,
        locator_pattern=request.locator_pattern,
    )
    granularity = "chunks_purged" if request.locator_kind else "documents_purged"
    return {"pattern": request.pattern, granularity: purged}


@router.delete("/{pattern:path}")
async def include(pattern: str, identity: RequestIdentity = Depends(get_identity)) -> dict:
    _require_employee(identity)
    use_case = build_manage_noindex_rules_use_case()
    await use_case.include(pattern)
    return {"pattern": pattern, "removed": True}


@router.get("", response_model=list[NoIndexRuleResponse])
async def list_rules(identity: RequestIdentity = Depends(get_identity)) -> list[NoIndexRuleResponse]:
    _require_employee(identity)
    use_case = build_manage_noindex_rules_use_case()
    rules = await use_case.list_rules()
    return [
        NoIndexRuleResponse(
            pattern=r.pattern,
            rule_type=r.rule_type,
            reason=r.reason,
            created_by=r.created_by,
            locator_kind=r.locator_kind,
            locator_pattern=r.locator_pattern,
            created_at=r.created_at,
        )
        for r in rules
    ]
