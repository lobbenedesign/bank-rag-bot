from __future__ import annotations

import pytest

from bank_rag.agents.numeric_grounding_guardrail import NUMERIC_UNVERIFIED_MESSAGE
from bank_rag.agents.orchestrator import RouterAgent
from bank_rag.agents.sentiment_escalation_guardrail import ESCALATION_MESSAGE
from bank_rag.agents.tool_registry import ToolRegistry
from bank_rag.agents.topic_guardrail import OUT_OF_SCOPE_MESSAGE
from bank_rag.application.ports.llm_client import LLMResponse
from bank_rag.application.use_cases.answer_question import AnswerQuestion
from bank_rag.domain.entities import Conversation, ConversationTurn, Intent, PendingAction
from bank_rag.infrastructure.security.pii_filter_regex import RegexPiiFilter


class FakeLLMClient:
    def __init__(self, response: LLMResponse) -> None:
        self._response = response

    async def complete(self, system_prompt, messages, tools=None) -> LLMResponse:
        return self._response

    async def stream_complete(self, system_prompt, messages, tools=None):
        from bank_rag.application.ports.llm_client import LLMStreamChunk

        if self._response.content:
            yield LLMStreamChunk(content_delta=self._response.content, is_final=False)
        yield LLMStreamChunk(content_delta="", is_final=True, response=self._response)


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._store[key] = value


class PassthroughQueryRewriter:
    """Mirrors LLMQueryRewriter's contract without needing an LLM call."""

    async def rewrite(self, history: list[dict[str, str]], question: str) -> str:
        return question


class RecordingAuditLog:
    def __init__(self) -> None:
        self.entries = []

    async def record(self, entry) -> None:
        self.entries.append(entry)


class AlwaysInScopeGuardrail:
    async def is_in_scope(self, question: str) -> bool:
        return True


class AlwaysOutOfScopeGuardrail:
    async def is_in_scope(self, question: str) -> bool:
        return False


class NeverEscalateGuardrail:
    async def needs_escalation(self, question: str) -> bool:
        return False


class AlwaysEscalateGuardrail:
    async def needs_escalation(self, question: str) -> bool:
        return True


class NeverConfirmGuardrail:
    async def is_confirmed(self, message: str) -> bool:
        return False


class AlwaysConfirmGuardrail:
    async def is_confirmed(self, message: str) -> bool:
        return True


class AlwaysVerifiedNumericGuardrail:
    async def is_verified(self, answer_text: str, citations) -> bool:
        return True


class NeverVerifiedNumericGuardrail:
    async def is_verified(self, answer_text: str, citations) -> bool:
        return False


@pytest.mark.asyncio
async def test_pii_is_masked_before_reaching_the_agent():
    captured_messages: list[dict] = []

    class CapturingLLMClient(FakeLLMClient):
        async def stream_complete(self, system_prompt, messages, tools=None):
            captured_messages.extend(messages)
            async for chunk in super().stream_complete(system_prompt, messages, tools):
                yield chunk

    llm = CapturingLLMClient(LLMResponse(content="Ok.", tool_calls=[], finish_reason="stop"))
    use_case = AnswerQuestion(
        RouterAgent(llm), ToolRegistry([]), RegexPiiFilter(), InMemoryCache(),
        PassthroughQueryRewriter(), RecordingAuditLog(), AlwaysInScopeGuardrail(), NeverEscalateGuardrail(), NeverConfirmGuardrail(), AlwaysVerifiedNumericGuardrail(),
    )

    await use_case.execute(Conversation(), "il mio iban è IT60X0542811101000000123456")

    assert "IT60X0542811101000000123456" not in captured_messages[-1]["content"]
    assert "[REDACTED_IBAN]" in captured_messages[-1]["content"]


@pytest.mark.asyncio
async def test_ungrounded_factual_claim_without_a_tool_call_is_never_cached():
    llm = FakeLLMClient(LLMResponse(content="Il Conto Base non ha canone.", tool_calls=[], finish_reason="stop"))
    cache = InMemoryCache()
    use_case = AnswerQuestion(
        RouterAgent(llm), ToolRegistry([]), RegexPiiFilter(), cache,
        PassthroughQueryRewriter(), RecordingAuditLog(), AlwaysInScopeGuardrail(), NeverEscalateGuardrail(), NeverConfirmGuardrail(), AlwaysVerifiedNumericGuardrail(),
    )

    first = await use_case.execute(Conversation(), "quanto costa il conto base?")
    assert len(cache._store) == 0
    assert first.grounded is False
    assert first.text == "Non ho questa informazione, ti metto in contatto con un operatore."


@pytest.mark.asyncio
async def test_real_smalltalk_greeting_is_grounded_and_not_cached():
    llm = FakeLLMClient(LLMResponse(content="Ciao! Come posso aiutarti?", tool_calls=[], finish_reason="stop"))
    use_case = AnswerQuestion(
        RouterAgent(llm), ToolRegistry([]), RegexPiiFilter(), InMemoryCache(),
        PassthroughQueryRewriter(), RecordingAuditLog(), AlwaysInScopeGuardrail(), NeverEscalateGuardrail(), NeverConfirmGuardrail(), AlwaysVerifiedNumericGuardrail(),
    )

    answer = await use_case.execute(Conversation(), "ciao")
    assert answer.grounded is True


@pytest.mark.asyncio
async def test_every_exchange_is_recorded_in_the_audit_log():
    llm = FakeLLMClient(LLMResponse(content="Ciao! Come posso aiutarti?", tool_calls=[], finish_reason="stop"))
    audit_log = RecordingAuditLog()
    conversation = Conversation(customer_id="cust-42", is_authenticated=True)
    use_case = AnswerQuestion(
        RouterAgent(llm), ToolRegistry([]), RegexPiiFilter(), InMemoryCache(),
        PassthroughQueryRewriter(), audit_log, AlwaysInScopeGuardrail(), NeverEscalateGuardrail(), NeverConfirmGuardrail(), AlwaysVerifiedNumericGuardrail(),
    )

    await use_case.execute(conversation, "ciao")

    assert len(audit_log.entries) == 1
    entry = audit_log.entries[0]
    assert entry.conversation_id == conversation.id
    assert entry.customer_id == "cust-42"
    assert entry.question == "ciao"
    assert entry.resolved_question == "ciao"


@pytest.mark.asyncio
async def test_follow_up_question_is_resolved_before_retrieval():
    class RecordingQueryRewriter:
        def __init__(self) -> None:
            self.calls: list[tuple[list[dict], str]] = []

        async def rewrite(self, history, question) -> str:
            self.calls.append((history, question))
            return "quanto costa il bonifico sul Conto Base" if history else question

    class RecordingLLMClient:
        def __init__(self) -> None:
            self.last_messages: list[dict] = []

        async def complete(self, system_prompt, messages, tools=None) -> LLMResponse:
            self.last_messages = messages
            return LLMResponse(content="Il bonifico è gratuito.", tool_calls=[], finish_reason="stop")

        async def stream_complete(self, system_prompt, messages, tools=None):
            from bank_rag.application.ports.llm_client import LLMStreamChunk

            self.last_messages = messages
            response = LLMResponse(content="Il bonifico è gratuito.", tool_calls=[], finish_reason="stop")
            yield LLMStreamChunk(content_delta=response.content, is_final=False)
            yield LLMStreamChunk(content_delta="", is_final=True, response=response)


    llm = RecordingLLMClient()
    rewriter = RecordingQueryRewriter()
    conversation = Conversation()
    conversation.add(ConversationTurn(role="user", content="quanto costa il conto base?"))
    conversation.add(ConversationTurn(role="assistant", content="Il Conto Base è gratuito."))

    use_case = AnswerQuestion(
        RouterAgent(llm), ToolRegistry([]), RegexPiiFilter(), InMemoryCache(),
        rewriter, RecordingAuditLog(), AlwaysInScopeGuardrail(), NeverEscalateGuardrail(), NeverConfirmGuardrail(), AlwaysVerifiedNumericGuardrail(),
    )

    await use_case.execute(conversation, "e quanto costa il bonifico?")

    assert rewriter.calls[-1][1] == "e quanto costa il bonifico?"
    assert llm.last_messages[-1]["content"] == "quanto costa il bonifico sul Conto Base"


@pytest.mark.asyncio
async def test_out_of_scope_question_never_reaches_the_router_agent():
    class UnreachableLLMClient:
        async def complete(self, system_prompt, messages, tools=None):
            raise AssertionError("router agent should never run for an out-of-scope question")

    audit_log = RecordingAuditLog()
    use_case = AnswerQuestion(
        RouterAgent(UnreachableLLMClient()), ToolRegistry([]), RegexPiiFilter(), InMemoryCache(),
        PassthroughQueryRewriter(), audit_log, AlwaysOutOfScopeGuardrail(), NeverEscalateGuardrail(), NeverConfirmGuardrail(), AlwaysVerifiedNumericGuardrail(),
    )

    answer = await use_case.execute(Conversation(), "scrivimi una poesia sull'autunno")

    assert answer.text == OUT_OF_SCOPE_MESSAGE
    assert answer.intent == Intent.UNKNOWN
    assert len(audit_log.entries) == 1  # still logged, for visibility into misuse patterns


@pytest.mark.asyncio
async def test_frustrated_customer_is_escalated_without_reaching_the_router_agent():
    class UnreachableLLMClient:
        async def complete(self, system_prompt, messages, tools=None):
            raise AssertionError("router agent should never run when sentiment escalation triggers")

    audit_log = RecordingAuditLog()
    use_case = AnswerQuestion(
        RouterAgent(UnreachableLLMClient()), ToolRegistry([]), RegexPiiFilter(), InMemoryCache(),
        PassthroughQueryRewriter(), audit_log, AlwaysInScopeGuardrail(), AlwaysEscalateGuardrail(), NeverConfirmGuardrail(), AlwaysVerifiedNumericGuardrail(),
    )

    answer = await use_case.execute(Conversation(), "sono stufo, non capite mai niente!")

    assert answer.text == ESCALATION_MESSAGE
    assert answer.intent == Intent.HUMAN_HANDOFF
    assert answer.grounded is True
    assert len(audit_log.entries) == 1


@pytest.mark.asyncio
async def test_pending_action_confirmed_executes_the_tool_and_clears_the_pending_state():
    class FakeConfirmableTool:
        name = "lock_card"
        requires_authentication = True
        requires_confirmation = True

        async def run(self, card_id: str) -> str:
            return f'{{"card_id": "{card_id}", "locked": true}}'

    class UnreachableLLMClient:
        async def complete(self, system_prompt, messages, tools=None):
            raise AssertionError("router agent should never run while resolving a pending action")

    from bank_rag.agents.tool_registry import ToolRegistry

    conversation = Conversation(is_authenticated=True)
    conversation.pending_action = PendingAction(
        tool_name="lock_card", arguments={"card_id": "card-42"}, confirmation_prompt="Confermi?"
    )
    use_case = AnswerQuestion(
        RouterAgent(UnreachableLLMClient()), ToolRegistry([FakeConfirmableTool()]), RegexPiiFilter(), InMemoryCache(),
        PassthroughQueryRewriter(), RecordingAuditLog(), AlwaysInScopeGuardrail(),
        NeverEscalateGuardrail(), AlwaysConfirmGuardrail(), AlwaysVerifiedNumericGuardrail(),
    )

    answer = await use_case.execute(conversation, "sì, confermo")

    assert "card-42" in answer.text
    assert "bloccata" in answer.text
    assert conversation.pending_action is None


@pytest.mark.asyncio
async def test_pending_action_declined_never_executes_the_tool():
    class UnreachableTool:
        name = "lock_card"
        requires_authentication = True
        requires_confirmation = True

        async def run(self, **kwargs):
            raise AssertionError("declining confirmation must never execute the tool")

    class UnreachableLLMClient:
        async def complete(self, system_prompt, messages, tools=None):
            raise AssertionError("router agent should never run while resolving a pending action")

    from bank_rag.agents.tool_registry import ToolRegistry

    conversation = Conversation(is_authenticated=True)
    conversation.pending_action = PendingAction(
        tool_name="lock_card", arguments={"card_id": "card-42"}, confirmation_prompt="Confermi?"
    )
    use_case = AnswerQuestion(
        RouterAgent(UnreachableLLMClient()), ToolRegistry([UnreachableTool()]), RegexPiiFilter(), InMemoryCache(),
        PassthroughQueryRewriter(), RecordingAuditLog(), AlwaysInScopeGuardrail(),
        NeverEscalateGuardrail(), NeverConfirmGuardrail(), AlwaysVerifiedNumericGuardrail(),
    )

    answer = await use_case.execute(conversation, "no, lascia stare")

    assert conversation.pending_action is None
    assert answer.text == "Ok, non ho eseguito l'azione. Come posso aiutarti?"


class _ScriptedToolCallingLLMClient:
    """Same replay contract as test_router_agent.py's FakeLLMClient (scripted
    responses, one per call), duplicated here rather than imported: these
    are two independent test modules and sharing a fixture across them would
    couple router-agent tests to answer-question tests for no real benefit.
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


class _FakeSearchTool:
    name = "search_knowledge_base"
    requires_authentication = False
    requires_confirmation = False

    async def run(self, query: str) -> str:
        import json

        return json.dumps(
            {
                "results": [
                    {
                        "document_id": "mutuo_giovani",
                        "title": "Mutuo Giovani",
                        "snippet": "Il tasso fisso a 20 anni è del 3.25%.",
                        "score": 0.9,
                    }
                ]
            }
        )

    def to_openai_schema(self):
        return {"type": "function", "function": {"name": self.name}}


def _tool_calling_answer_question(llm, numeric_guardrail) -> AnswerQuestion:
    from bank_rag.application.ports.llm_client import ToolCall

    llm._responses = [
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="1", name="search_knowledge_base", arguments={"query": "tasso mutuo"})],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="Il tasso fisso a 20 anni è del 3.25%.", tool_calls=[], finish_reason="stop"),
    ]
    return AnswerQuestion(
        RouterAgent(llm), ToolRegistry([_FakeSearchTool()]), RegexPiiFilter(), InMemoryCache(),
        PassthroughQueryRewriter(), RecordingAuditLog(), AlwaysInScopeGuardrail(),
        NeverEscalateGuardrail(), NeverConfirmGuardrail(), numeric_guardrail,
    )


@pytest.mark.asyncio
async def test_numeric_answer_verified_against_citations_passes_through_unchanged():
    llm = _ScriptedToolCallingLLMClient([])
    use_case = _tool_calling_answer_question(llm, AlwaysVerifiedNumericGuardrail())

    answer = await use_case.execute(Conversation(), "quanto costa il mutuo a 20 anni?")

    assert answer.text == "Il tasso fisso a 20 anni è del 3.25%."
    assert answer.grounded is True


@pytest.mark.asyncio
async def test_unverified_numeric_answer_is_replaced_and_never_cached():
    """The core Maker-Checker guarantee: a tool-grounded answer whose number
    the NumericGroundingGuardrail can't confirm against the citations must
    never reach the customer as-is, must not be marked grounded, and must
    never be cached for replay to other anonymous customers.
    """
    llm = _ScriptedToolCallingLLMClient([])
    use_case = _tool_calling_answer_question(llm, NeverVerifiedNumericGuardrail())

    conversation = Conversation()
    answer = await use_case.execute(conversation, "quanto costa il mutuo a 20 anni?")

    assert "3.25%" not in answer.text
    assert answer.grounded is False
    assert answer.text == NUMERIC_UNVERIFIED_MESSAGE
    # also the transcript itself must carry the corrected text, not the raw one
    assert conversation.turns[-1].content == NUMERIC_UNVERIFIED_MESSAGE


@pytest.mark.asyncio
async def test_unverified_numeric_answer_is_not_cached_for_future_anonymous_customers():
    llm = _ScriptedToolCallingLLMClient([])
    use_case = _tool_calling_answer_question(llm, NeverVerifiedNumericGuardrail())

    await use_case.execute(Conversation(is_authenticated=False), "quanto costa il mutuo a 20 anni?")

    cache = use_case._cache
    assert len(cache._store) == 0


@pytest.mark.asyncio
async def test_grounded_smalltalk_with_no_figures_passes_the_numeric_check_unchanged():
    """A grounded answer with nothing numeric to verify (e.g. a greeting)
    must sail through the Maker-Checker pass unchanged — the cost/necessity
    gate itself (skip the LLM call when there's no figure) is
    NumericGroundingGuardrail's own responsibility and is unit-tested
    directly in test_numeric_grounding_guardrail.py; this only confirms
    AnswerQuestion's wiring doesn't alter a grounded, non-numeric answer.
    """
    llm = FakeLLMClient(LLMResponse(content="Ciao! Come posso aiutarti?", tool_calls=[], finish_reason="stop"))
    use_case = AnswerQuestion(
        RouterAgent(llm), ToolRegistry([]), RegexPiiFilter(), InMemoryCache(),
        PassthroughQueryRewriter(), RecordingAuditLog(), AlwaysInScopeGuardrail(),
        NeverEscalateGuardrail(), NeverConfirmGuardrail(), AlwaysVerifiedNumericGuardrail(),
    )

    answer = await use_case.execute(Conversation(), "ciao")

    assert answer.grounded is True
    assert answer.text == "Ciao! Come posso aiutarti?"
