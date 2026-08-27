"""Redis-backed conversation store, replacing the in-memory dict placeholder
that previously lived in interface/api/routers/chat.py — a dict in a single
process is lost on restart/redeploy and never shared across replicas, which
breaks multi-turn conversations behind a load balancer.

TTL expiry (`ttl_seconds`) is deliberate: conversation history is transient
UX state, not a system of record — nothing here needs to survive forever.
"""
from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from redis.asyncio import Redis

from bank_rag.domain.entities import Conversation, ConversationTurn


class RedisConversationRepository:
    def __init__(self, redis: Redis, ttl_seconds: int = 86_400) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def get(self, conversation_id: UUID) -> Conversation | None:
        raw = await self._redis.get(self._key(conversation_id))
        if raw is None:
            return None
        return self._deserialize(raw)

    async def save(self, conversation: Conversation) -> None:
        await self._redis.set(self._key(conversation.id), self._serialize(conversation), ex=self._ttl)

    @staticmethod
    def _key(conversation_id: UUID) -> str:
        return f"conversation:{conversation_id}"

    @staticmethod
    def _serialize(conversation: Conversation) -> str:
        return json.dumps(
            {
                "id": str(conversation.id),
                "customer_id": conversation.customer_id,
                "is_authenticated": conversation.is_authenticated,
                "turns": [
                    {"role": t.role, "content": t.content, "timestamp": t.timestamp.isoformat()}
                    for t in conversation.turns
                ],
            }
        )

    @staticmethod
    def _deserialize(raw: str | bytes) -> Conversation:
        payload = json.loads(raw)
        conversation = Conversation(
            id=UUID(payload["id"]),
            customer_id=payload["customer_id"],
            is_authenticated=payload["is_authenticated"],
        )
        conversation.turns = [
            ConversationTurn(role=t["role"], content=t["content"], timestamp=datetime.fromisoformat(t["timestamp"]))
            for t in payload["turns"]
        ]
        return conversation
