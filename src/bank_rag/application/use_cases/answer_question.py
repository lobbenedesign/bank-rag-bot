"""Use case: AnswerQuestion. The only entry point the interface layer calls.

Transport-agnostic on purpose — a REST endpoint, a WebSocket handler and a
batch evaluation script all call the exact same use case, so behavior can't
drift between them.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from bank_rag.agents.confirmation_guardrail import ConfirmationGuardrail
from bank_rag.agents.orchestrator import RouterAgent
from bank_rag.agents.sentiment_escalation_guardrail import ESCALATION_MESSAGE, SentimentEscalationGuardrail
from bank_rag.agents.tool_registry import ToolRegistry
from bank_rag.agents.topic_guardrail import OUT_OF_SCOPE_MESSAGE, TopicGuardrail
from bank_rag.application.ports.audit_log import AuditLog
from bank_rag.application.ports.cache import ResponseCache
from bank_rag.application.ports.pii_filter import PiiFilter
from bank_rag.application.ports.query_rewriter import QueryRewriter
from bank_rag.domain.entities import Answer, AuditEntry, Conversation, ConversationTurn, Intent
from bank_rag.observability.tracing import trace_span

CACHEABLE_TTL_SECONDS = 3600
ACTION_UNAVAILABLE_MESSAGE = "Questa azione non è più disponibile. Come posso aiutarti?"
ACTION_DECLINED_MESSAGE = "Ok, non ho eseguito l'azione. Come posso aiutarti?"
ACTION_FAILED_MESSAGE = "Non sono riuscito a completare l'operazione. Ti metto in contatto con un operatore."


class AnswerQuestion:
    def __init__(
        self,
        router_agent: RouterAgent,
        tool_registry: ToolRegistry,
        pii_filter: PiiFilter,
        cache: ResponseCache,
        query_rewriter: QueryRewriter,
        audit_log: AuditLog,
        topic_guardrail: TopicGuardrail,
        sentiment_escalation: SentimentEscalationGuardrail,
        confirmation_guardrail: ConfirmationGuardrail,
    ) -> None:
        self._router_agent = router_agent
        self._tools = tool_registry
        self._pii_filter = pii_filter
        self._cache = cache
        self._query_rewriter = query_rewriter
        self._audit_log = audit_log
        self._topic_guardrail = topic_guardrail
        self._sentiment_escalation = sentiment_escalation
        self._confirmation_guardrail = confirmation_guardrail

    async def execute(self, conversation: Conversation, question: str) -> Answer:
        with trace_span("answer_question", conversation_id=str(conversation.id)):
            safe_question = self._pii_filter.mask(question)
            history_before = conversation.history_as_messages()
            conversation.add(ConversationTurn(role="user", content=safe_question))

            # Takes priority over every other guardrail: if a high-risk
            # action is awaiting confirmation, the customer's next message
            # IS the confirm/decline, not a fresh question. Running it
            # through TopicGuardrail first would risk misreading a bare
            # "sì" as off-topic and losing the pending action for no reason.
            if conversation.pending_action is not None:
                answer = await self._resolve_pending_action(conversation, safe_question)
                conversation.add(ConversationTurn(role="assistant", content=answer.text))
                await self._record_audit(conversation, safe_question, safe_question, answer)
                return answer

            if not await self._topic_guardrail.is_in_scope(safe_question):
                answer = Answer(text=OUT_OF_SCOPE_MESSAGE, citations=[], intent=Intent.UNKNOWN, grounded=True)
                conversation.add(ConversationTurn(role="assistant", content=answer.text))
                await self._record_audit(conversation, safe_question, safe_question, answer)
                return answer

            if await self._sentiment_escalation.needs_escalation(safe_question):
                answer = Answer(text=ESCALATION_MESSAGE, citations=[], intent=Intent.HUMAN_HANDOFF, grounded=True)
                conversation.add(ConversationTurn(role="assistant", content=answer.text))
                await self._record_audit(conversation, safe_question, safe_question, answer)
                return answer

            resolved_question = await self._query_rewriter.rewrite(history_before, safe_question)

            cache_key = self._cache_key(conversation, resolved_question)
            if not conversation.is_authenticated:
                cached = await self._cache.get(cache_key)
                if cached is not None:
                    return Answer(**json.loads(cached))

            answer = await self._router_agent.handle(conversation, self._tools, resolved_question)
            conversation.add(ConversationTurn(role="assistant", content=answer.text))
            conversation.pending_action = answer.pending_action

            if not conversation.is_authenticated and answer.grounded and answer.pending_action is None:
                await self._cache.set(cache_key, json.dumps(answer.__dict__, default=str), CACHEABLE_TTL_SECONDS)

            await self._record_audit(conversation, safe_question, resolved_question, answer)
            return answer

    async def _resolve_pending_action(self, conversation: Conversation, reply: str) -> Answer:
        pending = conversation.pending_action
        conversation.pending_action = None  # always cleared — executed, declined, or unavailable, never re-asked silently

        allowed_tools = {t.name: t for t in self._tools.for_conversation(conversation.is_authenticated)}
        tool = allowed_tools.get(pending.tool_name)
        if tool is None:
            return Answer(text=ACTION_UNAVAILABLE_MESSAGE, citations=[], intent=Intent.UNKNOWN, grounded=True)

        if not await self._confirmation_guardrail.is_confirmed(reply):
            return Answer(text=ACTION_DECLINED_MESSAGE, citations=[], intent=Intent.UNKNOWN, grounded=True)

        raw_result = await tool.run(**pending.arguments)
        return Answer(
            text=self._describe_tool_result(raw_result), citations=[], intent=Intent.ACCOUNT_BALANCE, grounded=True
        )

    @staticmethod
    def _describe_tool_result(raw_result: str) -> str:
        try:
            data = json.loads(raw_result)
        except json.JSONDecodeError:
            return ACTION_FAILED_MESSAGE
        if "error" in data:
            return ACTION_FAILED_MESSAGE
        if "locked" in data and data["locked"]:
            return f"Fatto — la carta {data.get('card_id', '')} è stata bloccata."
        return "Operazione completata."

    async def _record_audit(
        self, conversation: Conversation, question: str, resolved_question: str, answer: Answer
    ) -> None:
        await self._audit_log.record(
            AuditEntry(
                id=uuid4(),
                conversation_id=conversation.id,
                customer_id=conversation.customer_id,
                question=question,
                resolved_question=resolved_question,
                retrieved_document_ids=[c.document_id for c in answer.citations],
                answer_text=answer.text,
                intent=answer.intent,
                grounded=answer.grounded,
                created_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    def _cache_key(conversation: Conversation, resolved_question: str) -> str:
        # Keyed on the *resolved* standalone question, not the raw follow-up
        # text — "e quanto costa il bonifico?" would otherwise collide across
        # unrelated conversations with a meaningless cache hit/miss.
        raw = f"{len(conversation.turns)}::{resolved_question.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()
