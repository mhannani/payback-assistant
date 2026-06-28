"""The LangGraph checkpointer — durable conversation state in Postgres.

A checkpointer persists the graph's state per ``thread_id`` so a paused (clarify) conversation
can be resumed later — even after a restart or on a different instance. We use Postgres (the
database the service already runs) so paused threads are durable, not lost when the process
recycles. This is the production-grade replacement for an in-process ``MemorySaver``, which only
survives within one running process.

Lifecycle is owned by an ``async with`` context manager, the pattern LangGraph documents: the
pool (and thus the checkpointer) is opened on enter and closed on exit. The FastAPI lifespan
holds it open for the app's lifetime — no module-level globals to fall out of sync, no manual
close to forget.

Driver note: LangGraph's Postgres saver speaks **psycopg (v3)**, a different driver than the
``asyncpg`` SQLAlchemy uses for the catalog — hence the plain ``postgresql://`` DSN
(``settings.checkpoint_db_url``), and ``psycopg[binary]`` so the libpq wrapper is bundled.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.config import get_settings


@asynccontextmanager
async def checkpointer_pool() -> AsyncIterator[AsyncPostgresSaver]:
    """Yield an opened Postgres checkpointer for the duration of the ``async with`` block.

    ``autocommit=True`` is required: ``setup()`` issues ``CREATE INDEX CONCURRENTLY``, which
    Postgres refuses to run inside a transaction. The pool opens on enter and closes on exit, so
    the caller (the app lifespan) controls exactly how long it lives.
    """
    async with AsyncConnectionPool(
        conninfo=get_settings().checkpoint_db_url,
        max_size=10,
        kwargs={"autocommit": True},
    ) as pool:
        checkpointer = AsyncPostgresSaver(conn=pool)
        await checkpointer.setup()  # creates the checkpoint tables on first run; idempotent after
        yield checkpointer
