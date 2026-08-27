"""Unit tests for RouterAgent using fake LLMClient/Tool implementations —
zero network, zero mocking framework needed, because everything the agent
touches is a Protocol. This is the concrete payoff of the ports/adapters split.
"""
from __future__ import annotations

import json

import pytest

from bank_rag.agents.orchestrator import FALLBACK_TEXT, RouterAgent
from bank_rag.agents.tool_registry import ToolRegistry
from bank_rag.application.ports.llm_client import LLMResponse, ToolCall
from bank_rag.domain.entities import Conversation, ConversationTurn, Intent


class FakeLLMClient:
    """Replays a scripted sequence of responses, one per `complete()` call."""

    def __init__(self, scripted_responses: list[LLMResponse]) -> None:
        self._responses = list(scripted_responses)

    async def complete(self, system_prompt, messages, tools=None) -> LLMResponse:
        return self._responses.pop(0)


class FakeSearchTool:
    name = "search_knowledge_base"
    requires_authentication = False
    requires_confirmation = False

    async def run(self, query: str) -> str:
        return json.dumps(
            {"results": [{"document_id": "faq_1", "title": "Conto Base", "snippet": "Nessun canone.", "score": 0.9}]}
        )

    def to_openai_schema(self):
        return {"type": "function", "function": {"name": self.name}}


class FakeConfirmableTool:
    name = "lock_card"
    description = "Locks a card. First sentence describes the action."
    requires_authentication = True
    requires_confirmation = True

    async def run(self, **kwargs):
        raise AssertionError("run() must never be called for a requires_confirmation tool without confirmation")

    def to_openai_schema(self):
        return {"type": "function", "function": {"name": self.name}}


@pytest.mark.asyncio
async def test_answers_directly_without_tools_are_treated_as_smalltalk():
    llm = FakeLLMClient([LLMResponse(content="Ciao! Come posso aiutarti?", tool_calls=[], finish_reason="stop")])
    agent = RouterAgent(llm)
    conversation = Conversation()
    conversation.add(ConversationTurn(role="user", content="ciao"))

    answer = await agent.handle(conversation, ToolRegistry([]))

    assert answer.intent == Intent.SMALLTALK
    assert answer.grounded is True


@pytest.mark.asyncio
async def test_calls_search_tool_then_grounds_final_answer_in_its_result():
    llm = FakeLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="1", name="search_knowledge_base", arguments={"query": "conto base"})],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="Il Conto Base non ha canone mensile.", tool_calls=[], finish_reason="stop"),
        ]
    )
    agent = RouterAgent(llm)
    conversation = Conversation()
    conversation.add(ConversationTurn(role="user", content="quanto costa il conto base?"))

    answer = await agent.handle(conversation, ToolRegistry([FakeSearchTool()]))

    assert answer.grounded is True
    assert answer.citations[0].document_id == "faq_1"


@pytest.mark.asyncio
async def test_falls_back_to_human_handoff_when_answer_ungrounded():
    # LLM tries to answer with a factual-looking statement but never called a tool.
    llm = FakeLLMClient(
        [LLMResponse(content="Il tasso è del 3.5%.", tool_calls=[], finish_reason="stop")]
    )
    agent = RouterAgent(llm)
    conversation = Conversation()
    conversation.add(ConversationTurn(role="user", content="qual è il tasso del mutuo?"))

    answer = await agent.handle(conversation, ToolRegistry([]))

    assert answer.text == FALLBACK_TEXT
    assert answer.grounded is False


@pytest.mark.asyncio
async def test_tool_requiring_confirmation_is_proposed_not_executed():
    llm = FakeLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="1", name="lock_card", arguments={"card_id": "card-42"})],
                finish_reason="tool_calls",
            ),
        ]
    )
    agent = RouterAgent(llm)
    conversation = Conversation(is_authenticated=True)
    conversation.add(ConversationTurn(role="user", content="la mia carta è stata rubata, bloccala"))

    answer = await agent.handle(conversation, ToolRegistry([FakeConfirmableTool()]))

    # FakeConfirmableTool.run() would raise if called — reaching this
    # assertion at all proves .run() was never invoked.
    assert answer.pending_action is not None
    assert answer.pending_action.tool_name == "lock_card"
    assert answer.pending_action.arguments == {"card_id": "card-42"}
    assert answer.grounded is True
