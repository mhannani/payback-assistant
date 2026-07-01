"""Typed application settings, loaded from the environment.

A single ``Settings`` instance is the one place configuration is read, so the
rest of the code depends on typed attributes rather than raw ``os.environ``.
"""

from functools import lru_cache

from pydantic import Field
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
    # An explicit DSN takes precedence over the POSTGRES_* parts. Cloud SQL connects over a unix
    # socket (`...@/db?host=/cloudsql/INSTANCE`), a form the host:port builder can't express — so a
    # managed environment injects the full DSN here and the parts stay the builder for local/AWS.
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")

    # ── Embeddings ──────────────────────────────────────────────────
    # Which managed provider serves vectors: 'openai' (default) or 'vertex'. Embedding is a
    # cloud call, so a key/credentials are required (no offline model).
    embedding_provider: str = "openai"
    # Vertex project/region (env: VERTEXAI_PROJECT / VERTEXAI_LOCATION). Named to match LiteLLM's own
    # env vars for vertex_ai/* models, so ONE pair configures both our embedder's Vertex SDK AND the
    # agent's LLM through LiteLLM — no duplicate VERTEX_* vs VERTEXAI_* env vars.
    vertexai_project: str | None = None
    vertexai_location: str = "europe-west3"
    vertex_model: str = "text-multilingual-embedding-002"
    openai_api_key: str | None = None
    openai_model: str = "text-embedding-3-small"

    # ── Retrieval strategy selection ────────────────────────────────
    # The vector store, the candidate-filter, and the ranker are each pluggable; these
    # pick the active strategy so they can be swapped / A/B-compared by config alone.
    retriever_backend: str = "pgvector"  # pgvector (local/AWS) | bigquery (GCP warehouse tier)
    filter_strategy: str = "absolute"  # absolute | autocut | relative | none
    ranking_strategy: str = "constrained"  # constrained | mmr | zscore
    # BigQuery vector store — read only when retriever_backend=bigquery. The GCP project + location
    # come from the Vertex settings above (BigQuery and Vertex share the project).
    bigquery_dataset: str = "payback_vectors"
    bigquery_table: str = "products"

    # ── Retrieval tuning ────────────────────────────────────────────
    # Max cosine distance the 'absolute' filter keeps. Bound to the embedding model's
    # distance scale — re-derive (via `make eval`) if EMBEDDING_PROVIDER changes. Calibrated for
    # OpenAI text-embedding-3-small: relevant matches fall ~0.36–0.58, noise ~0.64+, so 0.60 sits
    # in the gap.
    filter_ceiling: float = 0.60
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
    def embedding_dim(self) -> int:
        """The vector dimension, derived from the configured provider + model (one source of truth).

        Sizes the schema column (db/init.sql via data.init_db) and the ORM column. Imported lazily
        to avoid a config→embeddings import cycle at module load.
        """
        from app.embeddings.dims import resolved_dimension

        return resolved_dimension(self)

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy DSN (asyncpg). The explicit override wins; else built from POSTGRES_*."""
        if self.database_url_override:
            return _as_async(self.database_url_override)
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def checkpoint_db_url(self) -> str:
        """Plain libpq DSN for the LangGraph Postgres checkpointer (psycopg, not SQLAlchemy).

        Same source as ``database_url`` but the libpq form (no ``+asyncpg``), so the checkpointer
        also reaches Cloud SQL over the socket when an override is set.
        """
        if self.database_url_override:
            return _as_libpq(self.database_url_override)
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# Both DSNs come from one source; these only rewrite the driver scheme and never touch the netloc
# or query, so a Cloud SQL socket form (`...@/db?host=/cloudsql/INSTANCE`) round-trips intact.
def _as_async(url: str) -> str:
    """Ensure the SQLAlchemy ``postgresql+asyncpg://`` scheme."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _as_libpq(url: str) -> str:
    """Strip the ``+asyncpg`` driver tag to the plain libpq ``postgresql://`` scheme psycopg wants."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
