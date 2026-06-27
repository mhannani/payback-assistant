"""Shared test fixtures.

Some tests run real SQL against Postgres because the features under test — pgvector
similarity and German full-text search — live in the database, not in Python. Those
tests use ``db_session``, which wraps each test in a transaction that is rolled back
at teardown, so they never pollute the seeded catalog and need no separate database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.embeddings import Embedder, get_embedder


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session in a transaction that is rolled back after the test.

    pytest-asyncio runs each test on its own event loop, but asyncpg connections are
    bound to the loop that opened them — a pooled connection reused on a later loop
    crashes on cleanup. So each test gets its own NullPool engine (no connection is
    pooled across loops) and disposes it at teardown. The outer transaction is rolled
    back, so nothing the test writes survives.
    """
    test_engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with test_engine.connect() as conn:
            txn = await conn.begin()
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                yield session
            finally:
                await session.close()
                await txn.rollback()
    finally:
        await test_engine.dispose()


@pytest.fixture(scope="session")
def embedder() -> Iterator[Embedder]:
    """One embedder for the whole test session (loading the model is the slow part)."""
    yield get_embedder()
