"""Pre-flight scope guardrail: rejects clearly off-topic questions before
spending a full tool-calling loop on them.

A separate, structural check — not just a persona instruction in the main
system prompt — because relying on the answering model's own judgment to
self-police scope is exactly the kind of guardrail that degrades under
unusual phrasing or prompt injection. Mirrors the "banking topic
classification" guardrail used in production banking-agent reference
architectures (e.g. mlrun's demo-banking-agent).

Cost trade-off, stated explicitly: this adds one extra LLM call per turn.
In production, this classification is simple enough to run on a much
smaller/cheaper model than the one used for the main answer — kept as the
same LLMClient here only for scaffold simplicity.
"""
from __future__ import annotations

from bank_rag.application.ports.llm_client import LLMClient

_CLASSIFIER_PROMPT = """Sei un classificatore. Rispondi ESATTAMENTE con
"true" o "false", nessun altro testo prima o dopo.

Il messaggio dell'utente riguarda servizi, prodotti, conto, carte, mutui,
pagamenti o assistenza di una banca? Rispondi "true" anche per saluti,
ringraziamenti o richieste di parlare con un operatore. Rispondi "false"
solo se il messaggio è chiaramente estraneo al contesto bancario (es.
richieste di scrivere codice, poesie, ricette, o opinioni su argomenti non
finanziari)."""

OUT_OF_SCOPE_MESSAGE = (
    "Posso aiutarti solo con domande sui servizi e prodotti della banca. "
    "Per altre richieste, contatta il supporto generale del sito."
)


class TopicGuardrail:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def is_in_scope(self, question: str) -> bool:
        response = await self._llm.complete(_CLASSIFIER_PROMPT, [{"role": "user", "content": question}])
        verdict = (response.content or "").strip().lower()
        # Fail OPEN on ambiguous/unexpected model output: a false negative
        # here just means the question proceeds to the main agent (which has
        # its own grounding guardrail); a false positive would incorrectly
        # block a legitimate banking question, which is the worse outcome
        # for a customer-facing bank chatbot.
        return verdict != "false"
