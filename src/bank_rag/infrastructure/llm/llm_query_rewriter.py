"""LLM-backed standalone-question rewriting.

Deliberately skips the LLM call entirely when there is no prior history —
the common case (first message of a conversation) costs zero extra latency
and zero extra tokens. In production this should run on a small/fast model
(this rewrite is a much simpler task than the main answer generation), kept
as a separate LLMClient instance rather than sharing the main chat model.
"""
from __future__ import annotations

from bank_rag.application.ports.llm_client import LLMClient

_REWRITE_SYSTEM_PROMPT = """Riscrivi l'ultima domanda dell'utente come una
domanda autonoma (standalone), che includa tutto il contesto necessario dalla
cronologia della conversazione, nella stessa lingua dell'utente.

Se la domanda è già autonoma, o non c'è cronologia rilevante, restituiscila
invariata. Rispondi SOLO con la domanda riscritta, senza commenti aggiuntivi."""


class LLMQueryRewriter:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def rewrite(self, history: list[dict[str, str]], question: str) -> str:
        if not history:
            return question

        response = await self._llm.complete(
            _REWRITE_SYSTEM_PROMPT, [*history, {"role": "user", "content": question}]
        )
        rewritten = (response.content or "").strip()
        return rewritten or question
