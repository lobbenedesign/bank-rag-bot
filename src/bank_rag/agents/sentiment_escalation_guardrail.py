"""Detects customer frustration/distress and escalates to a human operator
proactively — instead of only falling back after the RouterAgent's
`max_iterations` is exhausted (orchestrator.py), which can leave a genuinely
upset customer stuck through several more unhelpful tool-calling rounds
before finally being handed off.

Deliberately narrow scope: this classifies FRUSTRATION/ANGER/an explicit
request for a human, not "urgency" in general. "La mia carta è stata
rubata, puoi bloccarla?" should still reach the agent and its lock_card
tool — a calm, actionable request is exactly what the bot should handle
itself. "Sono stufo, non capite niente, voglio parlare con una persona" is
what this guardrail exists to catch immediately.

Found via research on production banking-chatbot architectures: mlrun's
demo-banking-agent scores sentiment on every turn to inform escalation;
industry guidance (Backbase's 2026 banking-chatbot report) calls this
"emotion-aware escalation."
"""
from __future__ import annotations

from bank_rag.application.ports.llm_client import LLMClient

_CLASSIFIER_PROMPT = """Sei un classificatore. Rispondi ESATTAMENTE con
"true" o "false", nessun altro testo prima o dopo.

Il messaggio del cliente esprime chiaramente frustrazione, rabbia, o una
richiesta esplicita di parlare con una persona/operatore? Rispondi "true"
SOLO in questi casi. Rispondi "false" per richieste normali, anche urgenti
o dirette (es. "la mia carta è stata rubata, bloccala subito" è "false" —
è una richiesta chiara e gestibile, non un segnale di frustrazione)."""

ESCALATION_MESSAGE = "Capisco la tua frustrazione. Ti metto subito in contatto con un operatore."


class SentimentEscalationGuardrail:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def needs_escalation(self, question: str) -> bool:
        response = await self._llm.complete(_CLASSIFIER_PROMPT, [{"role": "user", "content": question}])
        verdict = (response.content or "").strip().lower()
        # Fail CLOSED here — the opposite of TopicGuardrail's fail-open: an
        # unnecessary escalation just means the customer reaches a human
        # slightly earlier than strictly needed, while missing real distress
        # means leaving an upset customer stuck talking to a bot. The two
        # guardrails have opposite failure costs, so they fail in opposite
        # directions on purpose. Concretely: escalate unless the classifier
        # explicitly and unambiguously says "false".
        return verdict != "false"
