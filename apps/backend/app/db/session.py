"""Async database engine, session factory, and the FastAPI session dependency.

One engine and one session factory are created per process. ``get_session`` is
the dependency endpoints use to obtain a scoped ``AsyncSession`` that is closed
(and rolled back on error) automatically.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,  # transparently recover dropped connections
        future=True,
    )


engine: AsyncEngine = _build_engine()

SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped session; commit on success, roll back on error."""
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
