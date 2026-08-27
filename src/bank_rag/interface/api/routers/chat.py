from __future__ import annotations

from fastapi import APIRouter, Depends

from bank_rag.di_container import build_conversation_repository, get_settings
from bank_rag.domain.entities import Conversation
from bank_rag.interface.api.dependencies import (
    RequestIdentity,
    get_answer_question_use_case,
    get_identity,
    rate_limit,
)
from bank_rag.interface.api.schemas import ChatRequest, ChatResponse, CitationResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    dependencies=[Depends(rate_limit(get_settings().rate_limit_chat_per_minute, 60))],
)
async def send_message(
    request: ChatRequest,
    identity: RequestIdentity = Depends(get_identity),
) -> ChatResponse:
    conversations = build_conversation_repository()

    conversation = (
        (await conversations.get(request.conversation_id)) if request.conversation_id else None
    ) or Conversation(customer_id=identity.customer_id, is_authenticated=identity.is_authenticated)

    use_case = await get_answer_question_use_case(identity)
    answer = await use_case.execute(conversation, request.message)
    await conversations.save(conversation)

    return ChatResponse(
        conversation_id=conversation.id,
        answer=answer.text,
        citations=[CitationResponse(**c.__dict__) for c in answer.citations],
        grounded=answer.grounded,
    )
