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

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy DSN built from the discrete Postgres settings."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
