"""Shared test fixtures.

Some tests run real SQL against Postgres because the features under test — pgvector
similarity and German full-text search — live in the database, not in Python. Those
tests use ``db_session``, which wraps each test in a transaction that is rolled back
at teardown, so they never pollute the seeded catalog and need no separate database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session bound to a transaction that is rolled back after the test.

    Nothing the test writes survives, so DB-backed tests stay isolated from each
    other and from the seeded catalog.
    """
    async with engine.connect() as conn:
        txn = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await txn.rollback()
