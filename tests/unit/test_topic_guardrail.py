from __future__ import annotations

import pytest

from bank_rag.agents.topic_guardrail import TopicGuardrail
from bank_rag.application.ports.llm_client import LLMResponse


class FakeLLMClient:
    def __init__(self, content: str) -> None:
        self._content = content

    async def complete(self, system_prompt, messages, tools=None) -> LLMResponse:
        return LLMResponse(content=self._content, tool_calls=[], finish_reason="stop")


@pytest.mark.asyncio
async def test_in_scope_question_passes():
    guardrail = TopicGuardrail(FakeLLMClient("true"))
    assert await guardrail.is_in_scope("Quanto costa il conto base?") is True


@pytest.mark.asyncio
async def test_out_of_scope_question_is_rejected():
    guardrail = TopicGuardrail(FakeLLMClient("false"))
    assert await guardrail.is_in_scope("Scrivimi una poesia sull'autunno") is False


@pytest.mark.asyncio
async def test_ambiguous_or_malformed_classifier_output_fails_open():
    # Fail open, not closed: a false positive (blocking a real banking
    # question) is worse for a customer-facing bot than a false negative
    # (letting an off-topic question fall through to the main agent, which
    # has its own grounding guardrail anyway).
    guardrail = TopicGuardrail(FakeLLMClient("uhm, not sure, maybe true?"))
    assert await guardrail.is_in_scope("...") is True


@pytest.mark.asyncio
async def test_empty_classifier_response_fails_open():
    guardrail = TopicGuardrail(FakeLLMClient(""))
    assert await guardrail.is_in_scope("...") is True
