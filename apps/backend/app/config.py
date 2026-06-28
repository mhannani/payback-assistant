"""Typed application settings, loaded from the environment.

A single ``Settings`` instance is the one place configuration is read, so the
rest of the code depends on typed attributes rather than raw ``os.environ``.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"

    # ── Database (Postgres + pgvector) ──────────────────────────────
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "payback"
    postgres_user: str = "payback"
    postgres_password: str = "payback"

    # ── Embeddings ──────────────────────────────────────────────────
    # Which embedder serves vectors. 'local' (default) runs an offline
    # multilingual model so the service needs no credentials; 'vertex' / 'openai'
    # serve from those clouds (real impls, used only when configured).
    embedding_provider: str = "local"
    embedding_model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"
    # Cloud embedder settings — only read by the matching provider.
    vertex_project: str | None = None
    vertex_location: str = "europe-west3"
    vertex_model: str = "text-multilingual-embedding-002"
    openai_api_key: str | None = None
    openai_model: str = "text-embedding-3-small"

    # ── Retrieval strategy selection ────────────────────────────────
    # The vector store, the candidate-filter, and the ranker are each pluggable; these
    # pick the active strategy so they can be swapped / A/B-compared by config alone.
    retriever_backend: str = "pgvector"
    filter_strategy: str = "absolute"  # absolute | autocut | relative | none
    ranking_strategy: str = "constrained"  # constrained | mmr | zscore

    # ── Retrieval tuning ────────────────────────────────────────────
    # Max cosine distance the 'absolute' filter keeps. Bound to the embedding model's
    # distance scale — re-derive (via `make eval`) if EMBEDDING_PROVIDER changes.
    filter_ceiling: float = 0.50
    # Min ts_rank the keyword arm keeps, so its weak tail doesn't pollute fusion the way
    # the vector arm's tail (cut by filter_ceiling) does. 0.0 keeps every @@-match.
    fulltext_min_rank: float = 0.0

    # ── Intent agent LLM ────────────────────────────────────────────
    # The agent classifies a query through an LLM reached via a LiteLLM gateway.
    # `llm_model` is a LiteLLM model id; LiteLLM reads the matching provider
    # credentials from the environment (OPENAI_API_KEY here). Switching to
    # 'vertex_ai/gemini-2.0-flash', 'anthropic/claude-...', etc. is a one-line change.
    llm_model: str = "openai/gpt-4o-mini"
    llm_temperature: float = 0.0  # classification is deterministic, not creative

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy DSN built from the discrete Postgres settings."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def checkpoint_db_url(self) -> str:
        """Plain libpq DSN for the LangGraph Postgres checkpointer.

        LangGraph's checkpointer talks to Postgres through psycopg, not SQLAlchemy, so it needs
        the standard ``postgresql://`` URL — not the ``+asyncpg`` driver form above.
        """
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
