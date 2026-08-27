"""Composition root: the ONLY place that wires ports to concrete adapters.

Every other module in this codebase depends on Protocols, never on this file.
This keeps the dependency graph a strict one-way arrow:
  interface -> application -> domain
  infrastructure -> application (implements its ports)
Nothing in `application` or `agents` ever imports from `infrastructure`.
"""
from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI
from opensearchpy import AsyncOpenSearch
from qdrant_client import AsyncQdrantClient
from redis.asyncio import from_url as redis_from_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bank_rag.agents.confirmation_guardrail import ConfirmationGuardrail
from bank_rag.agents.orchestrator import RouterAgent
from bank_rag.agents.sentiment_escalation_guardrail import SentimentEscalationGuardrail
from bank_rag.agents.tool_registry import ToolRegistry
from bank_rag.agents.tools.account_balance_tool import AccountBalanceTool
from bank_rag.agents.tools.lock_card_tool import LockCardTool
from bank_rag.agents.tools.rag_search_tool import RagSearchTool
from bank_rag.agents.topic_guardrail import TopicGuardrail
from bank_rag.application.use_cases.answer_question import AnswerQuestion
from bank_rag.application.use_cases.ingest_document import IngestDocument
from bank_rag.application.use_cases.manage_noindex_rules import ManageNoIndexRules
from bank_rag.config.settings import Settings
from bank_rag.domain.entities import Audience
from bank_rag.infrastructure.bank_api.core_banking_client import CoreBankingHttpClient
from bank_rag.infrastructure.cache.redis_cache import RedisResponseCache
from bank_rag.infrastructure.embeddings.openai_embedder import OpenAiEmbedder
from bank_rag.infrastructure.keyword_index.opensearch_index import OpenSearchKeywordIndex
from bank_rag.infrastructure.llm.llm_query_rewriter import LLMQueryRewriter
from bank_rag.infrastructure.llm.openai_client import OpenAiChatClient
from bank_rag.infrastructure.persistence.document_repository_sql import SqlDocumentRepository
from bank_rag.infrastructure.persistence.redis_conversation_repository import RedisConversationRepository
from bank_rag.infrastructure.persistence.sql_audit_log import SqlAuditLog
from bank_rag.infrastructure.persistence.sql_noindex_registry import SqlNoIndexRegistry
from bank_rag.infrastructure.rerank.cross_encoder_reranker import CrossEncoderReranker
from bank_rag.infrastructure.security.pii_filter_regex import RegexPiiFilter
from bank_rag.infrastructure.security.prompt_injection_sanitizer import RegexPromptInjectionSanitizer
from bank_rag.infrastructure.security.redis_rate_limiter import RedisRateLimiter
from bank_rag.infrastructure.vector_stores.qdrant_store import QdrantVectorStore
from bank_rag.ingestion.chunking.semantic_chunker import SemanticChunker


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # populated from env/.env


def _new_sql_session() -> AsyncSession:
    # A short-lived session per composition, matching this codebase's request-
    # scoped use-case construction (see build_*_use_case below) — not shared
    # or pooled across requests.
    engine = create_async_engine(get_settings().postgres_dsn)
    return async_sessionmaker(engine)()


def build_answer_question_use_case(customer_id: str | None = None, is_authenticated: bool = False) -> AnswerQuestion:
    settings = get_settings()

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    embedder = OpenAiEmbedder(openai_client, model=settings.embedding_model)
    llm_client = OpenAiChatClient(openai_client, model=settings.chat_model)

    vector_store = QdrantVectorStore(AsyncQdrantClient(url=settings.qdrant_url), settings.qdrant_collection)
    keyword_index = OpenSearchKeywordIndex(AsyncOpenSearch(settings.opensearch_url), settings.opensearch_index)
    reranker = CrossEncoderReranker()

    allowed_audiences = [Audience.PUBLIC, Audience.INTERNAL] if is_authenticated else [Audience.PUBLIC]

    tools = [
        RagSearchTool(
            embedder, vector_store, keyword_index, reranker,
            allowed_audiences=allowed_audiences, top_k=settings.retrieval_top_k,
        )
    ]
    if is_authenticated and customer_id:
        bank_api = CoreBankingHttpClient(settings.core_banking_base_url, settings.core_banking_service_token)
        tools.append(AccountBalanceTool(bank_api, customer_id))
        tools.append(LockCardTool(bank_api, customer_id))

    router_agent = RouterAgent(llm_client, max_iterations=settings.router_max_iterations)
    cache = RedisResponseCache(redis_from_url(settings.redis_url))
    pii_filter = RegexPiiFilter()
    query_rewriter = LLMQueryRewriter(llm_client)
    audit_log = SqlAuditLog(_new_sql_session())
    topic_guardrail = TopicGuardrail(llm_client)
    sentiment_escalation = SentimentEscalationGuardrail(llm_client)
    confirmation_guardrail = ConfirmationGuardrail(llm_client)

    return AnswerQuestion(
        router_agent, ToolRegistry(tools), pii_filter, cache, query_rewriter, audit_log,
        topic_guardrail, sentiment_escalation, confirmation_guardrail,
    )


def build_ingest_document_use_case() -> IngestDocument:
    settings = get_settings()

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    embedder = OpenAiEmbedder(openai_client, model=settings.embedding_model)
    vector_store = QdrantVectorStore(AsyncQdrantClient(url=settings.qdrant_url), settings.qdrant_collection)
    keyword_index = OpenSearchKeywordIndex(AsyncOpenSearch(settings.opensearch_url), settings.opensearch_index)
    document_repository = SqlDocumentRepository(_new_sql_session())
    noindex_registry = SqlNoIndexRegistry(_new_sql_session())

    return IngestDocument(
        SemanticChunker(), embedder, vector_store, keyword_index, document_repository,
        content_sanitizer=RegexPromptInjectionSanitizer(),
        noindex_registry=noindex_registry,
    )


def build_manage_noindex_rules_use_case() -> ManageNoIndexRules:
    settings = get_settings()
    return ManageNoIndexRules(
        registry=SqlNoIndexRegistry(_new_sql_session()),
        vector_store=QdrantVectorStore(AsyncQdrantClient(url=settings.qdrant_url), settings.qdrant_collection),
        keyword_index=OpenSearchKeywordIndex(AsyncOpenSearch(settings.opensearch_url), settings.opensearch_index),
        document_repository=SqlDocumentRepository(_new_sql_session()),
    )


def build_noindex_registry() -> SqlNoIndexRegistry:
    return SqlNoIndexRegistry(_new_sql_session())


def build_document_repository() -> SqlDocumentRepository:
    return SqlDocumentRepository(_new_sql_session())


def build_rate_limiter() -> RedisRateLimiter:
    return RedisRateLimiter(redis_from_url(get_settings().redis_url))


def build_conversation_repository() -> RedisConversationRepository:
    settings = get_settings()
    return RedisConversationRepository(redis_from_url(settings.redis_url), ttl_seconds=settings.conversation_ttl_seconds)
