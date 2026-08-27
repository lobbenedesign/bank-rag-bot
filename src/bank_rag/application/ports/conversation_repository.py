from __future__ import annotations

from typing import Protocol
from uuid import UUID

from bank_rag.domain.entities import Conversation


class ConversationRepository(Protocol):
    async def get(self, conversation_id: UUID) -> Conversation | None: ...

    async def save(self, conversation: Conversation) -> None: ...
