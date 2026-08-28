from __future__ import annotations

import pytest

from bank_rag.agents.numeric_grounding_guardrail import NumericGroundingGuardrail
from bank_rag.application.ports.llm_client import LLMResponse
from bank_rag.domain.entities import Citation


class FakeLLMClient:
    def __init__(self, content: str) -> None:
        self._content = content

    async def complete(self, system_prompt, messages, tools=None) -> LLMResponse:
        return LLMResponse(content=self._content, tool_calls=[], finish_reason="stop")


class UnreachableLLMClient:
    async def complete(self, system_prompt, messages, tools=None):
        raise AssertionError("must not be called: no figure in the answer text, nothing to verify")


def _citation(snippet: str) -> Citation:
    return Citation(document_id="doc-1", title="Mutuo Giovani", snippet=snippet, score=0.9)


@pytest.mark.asyncio
async def test_answer_with_no_figures_skips_the_llm_call_entirely():
    """Cost gate, same reasoning as TopicGuardrail's own cost trade-off note:
    most turns have no numbers at all, so paying for a second LLM call on
    every single turn would be wasteful. UnreachableLLMClient proves the
    call never happens, not just that the result happens to be True.
    """
    guardrail = NumericGroundingGuardrail(UnreachableLLMClient())
    assert await guardrail.is_verified("Il bonifico è gratuito.", []) is True


@pytest.mark.asyncio
async def test_number_matching_the_citation_is_verified():
    guardrail = NumericGroundingGuardrail(FakeLLMClient("true"))
    citations = [_citation("Il tasso fisso a 20 anni è del 3.25%.")]
    assert await guardrail.is_verified("Il tasso fisso a 20 anni è del 3.25%.", citations) is True


@pytest.mark.asyncio
async def test_number_not_matching_any_citation_fails_verification():
    guardrail = NumericGroundingGuardrail(FakeLLMClient("false"))
    citations = [_citation("Il tasso fisso a 20 anni è del 3.25%.")]
    # model misquoted 3.25% as 2.05% — the classifier (scripted "false" here,
    # standing in for a real LLM catching the mismatch) must reject it
    assert await guardrail.is_verified("Il tasso fisso a 20 anni è del 2.05%.", citations) is False


@pytest.mark.asyncio
async def test_numeric_claim_with_zero_citations_is_never_verified():
    """A number with no source snippet at all can never be confirmed —
    fails without even asking the LLM (there is nothing to compare against)."""
    guardrail = NumericGroundingGuardrail(UnreachableLLMClient())
    assert await guardrail.is_verified("Il tasso è del 3.25%.", []) is False


@pytest.mark.asyncio
async def test_ambiguous_classifier_output_fails_closed():
    # Same fail-closed reasoning as SentimentEscalationGuardrail: an
    # unverifiable number reaching a bank customer is the worse outcome.
    guardrail = NumericGroundingGuardrail(FakeLLMClient("non sono sicuro"))
    citations = [_citation("Il tasso fisso a 20 anni è del 3.25%.")]
    assert await guardrail.is_verified("Il tasso fisso a 20 anni è del 3.25%.", citations) is False


def test_has_figure_recognizes_percentages_amounts_and_rate_acronyms():
    guardrail = NumericGroundingGuardrail(UnreachableLLMClient())
    assert guardrail.has_figure("Il tasso è del 3,25%.") is True
    assert guardrail.has_figure("Il TAEG è al 4%.") is True
    assert guardrail.has_figure("Costa 12,50 €.") is True
    assert guardrail.has_figure("Il bonifico è gratuito e immediato.") is False
