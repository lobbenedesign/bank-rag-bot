"""FastAPI dependency providers: identity resolution, rate limiting, and glue
to the DI composition root. Auth and abuse-prevention live at this edge on
purpose — the use-case/agent layer below never has to know a JWT exists.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request

from bank_rag.application.use_cases.answer_question import AnswerQuestion
from bank_rag.application.use_cases.ingest_document import IngestDocument
from bank_rag.di_container import (
    build_answer_question_use_case,
    build_ingest_document_use_case,
    build_rate_limiter,
    get_settings,
)
from bank_rag.infrastructure.security.jwt_auth import InvalidToken, decode_token


@dataclass(frozen=True)
class RequestIdentity:
    customer_id: str | None
    is_authenticated: bool
    is_employee: bool


async def get_identity(authorization: str | None = Header(default=None)) -> RequestIdentity:
    if authorization is None:
        return RequestIdentity(customer_id=None, is_authenticated=False, is_employee=False)

    token = authorization.removeprefix("Bearer ").strip()
    settings = get_settings()
    try:
        claims = decode_token(token, settings.jwt_secret, settings.jwt_algorithm, settings.jwt_audience)
    except InvalidToken as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc

    return RequestIdentity(customer_id=claims.subject, is_authenticated=True, is_employee=claims.is_employee)


def rate_limit(limit: int, window_seconds: int):
    """Dependency factory: keys the limit on customer_id when authenticated,
    falling back to client IP for anonymous traffic on public endpoints.
    """

    async def _check(request: Request, identity: RequestIdentity = Depends(get_identity)) -> None:
        limiter = build_rate_limiter()
        key = identity.customer_id or (request.client.host if request.client else "anonymous")
        if not await limiter.is_allowed(key, limit, window_seconds):
            raise HTTPException(status_code=429, detail="troppe richieste, riprova tra qualche istante")

    return _check


async def get_answer_question_use_case(identity: RequestIdentity) -> AnswerQuestion:
    return build_answer_question_use_case(
        customer_id=identity.customer_id, is_authenticated=identity.is_authenticated
    )


async def get_ingest_document_use_case() -> IngestDocument:
    return build_ingest_document_use_case()
