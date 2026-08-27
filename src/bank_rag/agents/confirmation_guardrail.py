"""Classifies whether a customer's reply explicitly confirms a previously
proposed high-risk action (a PendingAction on Conversation — see
domain/entities.py and RouterAgent's requires_confirmation handling).

Same pattern as TopicGuardrail and SentimentEscalationGuardrail (a small
LLM classifier behind a one-method class), same fail-mode as
SentimentEscalationGuardrail and for the same reason: executing an action
the customer didn't actually confirm is worse than asking again.
"""
from __future__ import annotations

from bank_rag.application.ports.llm_client import LLMClient

_CLASSIFIER_PROMPT = """Sei un classificatore. Rispondi ESATTAMENTE con
"true" o "false", nessun altro testo prima o dopo.

Il messaggio del cliente conferma esplicitamente un'azione precedentemente
proposta (es. "sì", "sì, confermo", "vai pure", "fallo")? Rispondi "true"
SOLO per una conferma chiara e inequivocabile. Rispondi "false" per
qualunque cosa non sia una conferma esplicita — incluse domande, richieste
diverse, esitazioni, o silenzio sull'argomento."""


class ConfirmationGuardrail:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def is_confirmed(self, message: str) -> bool:
        response = await self._llm.complete(_CLASSIFIER_PROMPT, [{"role": "user", "content": message}])
        verdict = (response.content or "").strip().lower()
        # Fail CLOSED: ambiguous output means NOT confirmed. Executing an
        # unconfirmed action is the failure this whole mechanism exists to
        # prevent — an unnecessary "let me ask again" is the safe direction
        # to fail in.
        return verdict == "true"
