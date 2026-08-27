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
    """Replays a scripted sequence of responses, one per `complete()`/
    `stream_complete()` call. `stream_complete` wraps each scripted response
    as a single content chunk followed by the final accumulated chunk —
    enough to exercise RouterAgent.handle_streaming's control flow without
    needing a real token-by-token stream.
    """

    def __init__(self, scripted_responses: list[LLMResponse]) -> None:
        self._responses = list(scripted_responses)

    async def complete(self, system_prompt, messages, tools=None) -> LLMResponse:
        return self._responses.pop(0)

    async def stream_complete(self, system_prompt, messages, tools=None):
        from bank_rag.application.ports.llm_client import LLMStreamChunk

        response = self._responses.pop(0)
        if response.content:
            yield LLMStreamChunk(content_delta=response.content, is_final=False)
        yield LLMStreamChunk(content_delta="", is_final=True, response=response)


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


class FakeNonSearchTool:
    """Stands in for any tool that isn't search_knowledge_base — e.g.
    get_account_balance or find_branches — to prove grounding isn't
    hardcoded to the search tool specifically.
    """

    name = "find_branches"
    requires_authentication = False
    requires_confirmation = False

    async def run(self, query: str) -> str:
        return json.dumps({"results": [{"name": "Filiale Milano Centro", "city": "Milano"}]})

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
async def test_non_search_tool_also_grounds_the_answer():
    # Regression test: grounding used to check `tool.name ==
    # "search_knowledge_base"` specifically, so a real answer built from
    # any OTHER tool's result (account balance, branch lookup, ...) was
    # silently replaced by FALLBACK_TEXT. Any successfully-invoked tool
    # must ground the turn.
    llm = FakeLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="1", name="find_branches", arguments={"query": "Milano"})],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="C'è una filiale a Milano Centro.", tool_calls=[], finish_reason="stop"),
        ]
    )
    agent = RouterAgent(llm)
    conversation = Conversation()
    conversation.add(ConversationTurn(role="user", content="dove trovo una filiale a Milano?"))

    answer = await agent.handle(conversation, ToolRegistry([FakeNonSearchTool()]))

    assert answer.grounded is True
    assert answer.text == "C'è una filiale a Milano Centro."


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


@pytest.mark.asyncio
async def test_streaming_buffers_the_first_ungrounded_answer_instead_of_revealing_it_live():
    # Regression guard for the exact hazard streaming introduces: if the raw
    # ungrounded model output ("Il tasso è del 3.5%.") were forwarded
    # token-by-token as it streamed in, it would already be visible to the
    # customer before the FALLBACK_TEXT swap could replace it. Assert the
    # only content ever emitted, in the single pre-done chunk, is the
    # swapped-in fallback — the real model text must never appear anywhere.
    llm = FakeLLMClient([LLMResponse(content="Il tasso è del 3.5%.", tool_calls=[], finish_reason="stop")])
    agent = RouterAgent(llm)
    conversation = Conversation()
    conversation.add(ConversationTurn(role="user", content="qual è il tasso del mutuo?"))

    events = [event async for event in agent.handle_streaming(conversation, ToolRegistry([]))]

    non_done_deltas = [e.delta for e in events if not e.done]
    assert non_done_deltas == [FALLBACK_TEXT]  # sent whole, in one chunk — never the raw ungrounded text
    assert "3.5%" not in "".join(non_done_deltas)
    assert events[-1].done is True
    assert events[-1].answer.text == FALLBACK_TEXT
    assert events[-1].answer.grounded is False


@pytest.mark.asyncio
async def test_streaming_reveals_content_live_once_search_has_grounded_the_turn():
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

    events = [event async for event in agent.handle_streaming(conversation, ToolRegistry([FakeSearchTool()]))]

    live_deltas = [e.delta for e in events if not e.done]
    assert "".join(live_deltas) == "Il Conto Base non ha canone mensile."
    assert events[-1].done is True
    assert events[-1].answer.grounded is True
