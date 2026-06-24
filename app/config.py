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

    # Dimensionality of the product/query embedding vectors.
    embedding_dim: int = Field(default=384)

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
