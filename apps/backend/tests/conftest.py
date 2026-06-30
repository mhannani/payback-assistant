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
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.embeddings import Embedder, get_embedder
from app.main import app

# Embeddings and the agent LLM are managed cloud calls, so tests that touch them need the
# configured provider's credential. The check is provider-agnostic: LiteLLM's validate_environment
# knows each provider's required env vars (an API key, or Vertex's project/ADC), so the suite skips
# (not fails) without credentials. Pure logic always runs (test_agent_logic.py, the hermetic
# embedder contract tests).


def _provider_credentials_present() -> bool:
    """True when the configured embedding provider and the agent LLM can both authenticate."""
    import litellm

    s = get_settings()
    embedding_model = (
        f"openai/{s.openai_model}"
        if s.embedding_provider == "openai"
        else f"vertex_ai/{s.vertex_model}"
    )
    return all(
        litellm.validate_environment(model=m)["keys_in_environment"]
        for m in (embedding_model, s.llm_model)
    )


requires_provider = pytest.mark.skipif(
    not _provider_credentials_present(),
    reason="needs the configured provider's credential — embeddings and the agent call it live",
)


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


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _dispose_app_engine() -> AsyncIterator[None]:
    """Dispose the app's module-level engine at session end.

    Under the shared session loop the app engine pools connections on that loop; disposing
    it within the loop avoids "Event loop is closed" warnings during interpreter shutdown.
    """
    yield
    from app.db.session import engine

    await engine.dispose()


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    """An async HTTP client for the app, run in-process via ASGI.

    The app's async DB engine is pooled and can't be shared across event loops, so the
    endpoints are exercised with httpx's AsyncClient (one event loop) rather than the sync
    TestClient (which spins a fresh loop per request and trips "event loop is closed").
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(scope="session")
def embedder() -> Iterator[Embedder]:
    """The configured (cloud) embedder for tests that compute real vectors.

    Embedding is a managed cloud call, so any test using this fixture needs the configured
    provider's credential; skip cleanly without it so the suite stays green credential-less.
    """
    if not _provider_credentials_present():
        pytest.skip("needs the configured provider's credential — embedding is a live cloud call")
    yield get_embedder()


@pytest_asyncio.fixture(scope="session")
async def agent_client() -> AsyncIterator[AsyncClient]:
    """An async client for the agent endpoints, with the app lifespan active.

    Runs the app's real ``lifespan`` (which opens the durable checkpointer and compiles the agent
    onto ``app.state``) for the whole agent-test session — the same setup the running app does.
    Session-scoped so the checkpointer pool is opened once and lives across all agent tests; the
    endpoints are stateless, so one shared client is safe.
    """
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
