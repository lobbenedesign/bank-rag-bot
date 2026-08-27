from __future__ import annotations

import pytest

from bank_rag.agents.confirmation_guardrail import ConfirmationGuardrail
from bank_rag.application.ports.llm_client import LLMResponse


class FakeLLMClient:
    def __init__(self, content: str) -> None:
        self._content = content

    async def complete(self, system_prompt, messages, tools=None) -> LLMResponse:
        return LLMResponse(content=self._content, tool_calls=[], finish_reason="stop")


@pytest.mark.asyncio
async def test_explicit_yes_is_confirmed():
    guardrail = ConfirmationGuardrail(FakeLLMClient("true"))
    assert await guardrail.is_confirmed("sì, confermo") is True


@pytest.mark.asyncio
async def test_unrelated_reply_is_not_confirmed():
    guardrail = ConfirmationGuardrail(FakeLLMClient("false"))
    assert await guardrail.is_confirmed("quanto costa il conto base?") is False


@pytest.mark.asyncio
async def test_ambiguous_classifier_output_fails_closed():
    guardrail = ConfirmationGuardrail(FakeLLMClient("forse"))
    assert await guardrail.is_confirmed("forse") is False


@pytest.mark.asyncio
async def test_empty_classifier_response_fails_closed():
    guardrail = ConfirmationGuardrail(FakeLLMClient(""))
    assert await guardrail.is_confirmed("...") is False
