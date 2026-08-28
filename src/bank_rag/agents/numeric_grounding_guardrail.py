"""Maker-Checker for numeric claims: verifies every rate/fee/percentage the
final answer states is literally present in the citations that backed it,
before that answer is trusted for caching or audit.

Why this exists on top of the existing `grounded` flag (orchestrator.py):
`grounded` only proves *a tool was called* and its result backed *some*
part of the answer — it does not prove the specific number the model wrote
down is the number that was actually in the source snippet. A model can
misread "3.5%" as "3.05%" while genuinely believing it is quoting its own
tool result faithfully; `grounded` stays True either way. This is the
Maker-Checker pattern banking-chatbot guidance recommends specifically for
financial figures: a second, independent, narrow-scope pass whose only job
is comparing digits, not writing prose — the same reasoning already applied
to TopicGuardrail and SentimentEscalationGuardrail, extended to numbers.

Known limitation, stated honestly (not hidden): by the time this guardrail
runs, the model's raw text may already have streamed live to the customer
token-by-token, if `RouterAgent` had already grounded the turn via a tool
call in an earlier iteration (see orchestrator.py's `can_reveal_live`) —
blocking that live reveal too would mean buffering the entire finishing
answer before ever showing a token, which conflicts with
`test_streaming_reveals_content_live_once_search_has_grounded_the_turn`
(deliberate, tested behavior). What this guardrail DOES guarantee: an
unverified numeric answer is never the text left on screen (the client
overwrites the live-streamed text with the final `done` event's answer —
see chat-ui.js's `onDone`), never cached for replay to other anonymous
customers, and never recorded in the audit trail as if it were grounded.
"""
from __future__ import annotations

import re

from bank_rag.application.ports.llm_client import LLMClient
from bank_rag.domain.entities import Citation

# Fires only when the answer actually contains something number-like — most
# turns (greetings, procedural answers with no figures) never pay for the
# extra LLM call. Same cost-transparency reasoning as TopicGuardrail.
_HAS_FIGURE = re.compile(r"\d+[.,]\d+\s*%|\d+\s*%|\bTAN\b|\bTAEG\b|€\s*\d|\d+[.,]\d+\s*€")

_VALIDATOR_PROMPT = """Sei un validatore numerico, non un assistente
conversazionale. Ti vengono forniti un TESTO DI RISPOSTA e uno o più
ESTRATTI SORGENTE. Rispondi ESATTAMENTE con "true" o "false", nessun altro
testo prima o dopo.

Rispondi "true" SOLO SE ogni numero (percentuale, tasso, importo, durata,
TAN, TAEG) citato nel TESTO DI RISPOSTA compare, con lo stesso valore
esatto, in almeno uno degli ESTRATTI SORGENTE. Rispondi "false" se anche un
solo numero nella risposta non trova riscontro esatto negli estratti, è
stato arrotondato diversamente, o è stato inventato."""

NUMERIC_UNVERIFIED_MESSAGE = (
    "Non riesco a confermare con certezza questo dato numerico sui documenti "
    "disponibili. Ti metto in contatto con un operatore per il valore esatto."
)


class NumericGroundingGuardrail:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    @staticmethod
    def has_figure(text: str) -> bool:
        return bool(_HAS_FIGURE.search(text))

    async def is_verified(self, answer_text: str, citations: list[Citation]) -> bool:
        if not self.has_figure(answer_text):
            return True  # nothing numeric to verify — not this guardrail's concern
        if not citations:
            return False  # a numeric claim with zero source snippets can never be verified

        sources = "\n---\n".join(c.snippet for c in citations)
        prompt = f"TESTO DI RISPOSTA:\n{answer_text}\n\nESTRATTI SORGENTE:\n{sources}"
        response = await self._llm.complete(_VALIDATOR_PROMPT, [{"role": "user", "content": prompt}])
        verdict = (response.content or "").strip().lower()
        # Fail CLOSED, same reasoning as SentimentEscalationGuardrail: an
        # unverifiable number reaching a bank customer costs more than an
        # occasional unnecessary handoff for a number that was actually correct.
        return verdict == "true"
