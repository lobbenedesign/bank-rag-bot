"""Round-trip tests for the (de)serialization logic only — _serialize and
_deserialize are static methods with no Redis dependency, so this exercises
the real code without needing a live Redis instance.

Written specifically to catch the class of bug found while wiring the
confirmation flow: pending_action was silently dropped by serialization,
which no test with a fake ConversationRepository (a dict in memory) could
ever catch, because a fake never actually serializes anything.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from bank_rag.domain.entities import Conversation, ConversationTurn, PendingAction
from bank_rag.infrastructure.persistence.redis_conversation_repository import RedisConversationRepository


def test_round_trip_preserves_turns_and_no_pending_action():
    conversation = Conversation(customer_id="cust-42", is_authenticated=True)
    conversation.add(ConversationTurn(role="user", content="ciao", timestamp=datetime.now(timezone.utc)))
    conversation.add(ConversationTurn(role="assistant", content="Ciao!", timestamp=datetime.now(timezone.utc)))

    raw = RedisConversationRepository._serialize(conversation)
    restored = RedisConversationRepository._deserialize(raw)

    assert restored.id == conversation.id
    assert restored.customer_id == "cust-42"
    assert restored.is_authenticated is True
    assert [t.content for t in restored.turns] == ["ciao", "Ciao!"]
    assert restored.pending_action is None


def test_round_trip_preserves_pending_action():
    # This is exactly the scenario an HTTP round trip needs: propose
    # lock_card in request 1, persist to Redis, load it back fresh in
    # request 2 to resolve the confirmation.
    conversation = Conversation(id=uuid4(), customer_id="cust-42", is_authenticated=True)
    conversation.pending_action = PendingAction(
        tool_name="lock_card",
        arguments={"card_id": "card-42"},
        confirmation_prompt="Confermi di voler bloccare la carta card-42?",
    )

    raw = RedisConversationRepository._serialize(conversation)
    restored = RedisConversationRepository._deserialize(raw)

    assert restored.pending_action is not None
    assert restored.pending_action.tool_name == "lock_card"
    assert restored.pending_action.arguments == {"card_id": "card-42"}
    assert restored.pending_action.confirmation_prompt == "Confermi di voler bloccare la carta card-42?"
