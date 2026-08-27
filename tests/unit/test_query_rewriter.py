from __future__ import annotations

import pytest

from bank_rag.application.ports.llm_client import LLMResponse
from bank_rag.infrastructure.llm.llm_query_rewriter import LLMQueryRewriter


class UnreachableLLMClient:
    """Raises if called — proves the rewriter skips the LLM entirely when
    there is no conversation history (the common, latency-sensitive case).
    """

    async def complete(self, system_prompt, messages, tools=None):
        raise AssertionError("LLM should not be called when history is empty")


class FakeLLMClient:
    def __init__(self, content: str) -> None:
        self._content = content

    async def complete(self, system_prompt, messages, tools=None) -> LLMResponse:
        return LLMResponse(content=self._content, tool_calls=[], finish_reason="stop")


@pytest.mark.asyncio
async def test_skips_llm_call_when_no_history():
    rewriter = LLMQueryRewriter(UnreachableLLMClient())
    result = await rewriter.rewrite([], "quanto costa il conto base?")
    assert result == "quanto costa il conto base?"


@pytest.mark.asyncio
async def test_resolves_follow_up_using_history():
    rewriter = LLMQueryRewriter(FakeLLMClient("quanto costa il bonifico sul Conto Base"))
    history = [
        {"role": "user", "content": "quanto costa il conto base?"},
        {"role": "assistant", "content": "Il Conto Base è gratuito."},
    ]
    result = await rewriter.rewrite(history, "e il bonifico?")
    assert result == "quanto costa il bonifico sul Conto Base"


@pytest.mark.asyncio
async def test_falls_back_to_original_question_on_empty_llm_response():
    rewriter = LLMQueryRewriter(FakeLLMClient(""))
    history = [{"role": "user", "content": "ciao"}]
    result = await rewriter.rewrite(history, "e il bonifico?")
    assert result == "e il bonifico?"
