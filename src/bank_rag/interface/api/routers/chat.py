from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

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


@router.post(
    "/stream",
    dependencies=[Depends(rate_limit(get_settings().rate_limit_chat_per_minute, 60))],
)
async def send_message_streaming(
    request: ChatRequest,
    identity: RequestIdentity = Depends(get_identity),
) -> StreamingResponse:
    """Server-Sent Events variant of POST /chat. Each event is a JSON line:
    `{"type": "delta", "text": "..."}` while the answer is being generated,
    then exactly one `{"type": "done", ...}` carrying the full answer,
    citations, and conversation id — mirrors ChatResponse's fields so a
    client can treat the done event as "the same response, just after
    watching it arrive."
    """
    conversations = build_conversation_repository()

    conversation = (
        (await conversations.get(request.conversation_id)) if request.conversation_id else None
    ) or Conversation(customer_id=identity.customer_id, is_authenticated=identity.is_authenticated)

    use_case = await get_answer_question_use_case(identity)

    async def event_stream():
        async for event in use_case.execute_streaming(conversation, request.message):
            if not event.done:
                yield f"data: {json.dumps({'type': 'delta', 'text': event.delta})}\n\n"
                continue

            await conversations.save(conversation)
            answer = event.answer
            payload = {
                "type": "done",
                "conversation_id": str(conversation.id),
                "answer": answer.text,
                "citations": [c.__dict__ for c in answer.citations],
                "grounded": answer.grounded,
            }
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
