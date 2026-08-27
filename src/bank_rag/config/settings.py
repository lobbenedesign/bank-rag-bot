from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    openai_api_key: str
    chat_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "bank_documents"

    opensearch_url: str = "http://localhost:9200"
    opensearch_index: str = "bank_documents"

    redis_url: str = "redis://localhost:6379/0"

    postgres_dsn: str = "postgresql+asyncpg://bank_rag:bank_rag@localhost:5432/bank_rag"

    core_banking_base_url: str
    core_banking_service_token: str

    allowed_scrape_domain: str = "www.example-bank.it"
    router_max_iterations: int = 4
    retrieval_top_k: int = 5

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_audience: str | None = None

    rate_limit_chat_per_minute: int = 20
    rate_limit_admin_per_minute: int = 10

    conversation_ttl_seconds: int = 86_400
