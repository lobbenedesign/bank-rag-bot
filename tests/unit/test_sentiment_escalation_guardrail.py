from __future__ import annotations

import pytest

from bank_rag.agents.sentiment_escalation_guardrail import SentimentEscalationGuardrail
from bank_rag.application.ports.llm_client import LLMResponse


class FakeLLMClient:
    def __init__(self, content: str) -> None:
        self._content = content

    async def complete(self, system_prompt, messages, tools=None) -> LLMResponse:
        return LLMResponse(content=self._content, tool_calls=[], finish_reason="stop")


@pytest.mark.asyncio
async def test_frustrated_message_triggers_escalation():
    guardrail = SentimentEscalationGuardrail(FakeLLMClient("true"))
    assert await guardrail.needs_escalation("Sono stufo, non capite mai niente, voglio un operatore!") is True


@pytest.mark.asyncio
async def test_calm_actionable_request_does_not_trigger_escalation():
    guardrail = SentimentEscalationGuardrail(FakeLLMClient("false"))
    assert await guardrail.needs_escalation("La mia carta è stata rubata, puoi bloccarla?") is False


@pytest.mark.asyncio
async def test_ambiguous_classifier_output_fails_closed():
    # Opposite of TopicGuardrail's fail-open: missing real distress is worse
    # than an unnecessary early handoff, so ambiguous output here escalates.
    guardrail = SentimentEscalationGuardrail(FakeLLMClient("non sono sicuro"))
    assert await guardrail.needs_escalation("...") is True


@pytest.mark.asyncio
async def test_empty_classifier_response_fails_closed():
    guardrail = SentimentEscalationGuardrail(FakeLLMClient(""))
    assert await guardrail.needs_escalation("...") is True
