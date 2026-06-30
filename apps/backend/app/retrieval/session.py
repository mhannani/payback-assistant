"""The session-provider type retrievers use to own their Postgres access.

A retriever is process-cached (built once) while a database session is request-scoped, so a session
can't be baked into the retriever's constructor. Instead it takes a *provider* — a zero-arg callable
returning a fresh session context manager (the app's ``SessionFactory`` satisfies this directly) —
and opens a short read transaction per ``search``. This keeps the session out of the ``Retriever``
interface entirely: each backend owns its data access, and tests inject a provider for the
rolled-back test session.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]
