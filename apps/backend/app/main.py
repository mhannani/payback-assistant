"""Application entrypoint: the FastAPI app and its top-level routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.checkpointer import checkpointer_pool
from app.agent.graph import compile_agent
from app.agent.runner import UnknownThreadError, resume_assist, start_assist
from app.db.session import get_session
from app.retrieval.base import Retriever
from app.retrieval.factory import get_retriever
from app.retrieval.types import Sort
from app.schemas import AssistResponse, ProductOut
from app.shared.partner import PartnerSlug


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App lifecycle: open the durable checkpointer, compile the agent once, store on app.state.

    The checkpointer's pool lives for exactly the app's lifetime via this ``async with``; the
    compiled agent (stateless, thread-safe) is built once here and reused for every request, with
    per-conversation state kept in the checkpointer by ``thread_id``.
    """
    async with checkpointer_pool() as checkpointer:
        app.state.agent = compile_agent(checkpointer)
        yield


def get_app_agent(request: Request):
    """Dependency: the compiled agent, built at startup and held on app state."""
    return request.app.state.agent


app = FastAPI(
    title="PAYBACK Assistant",
    summary="Multilingual product assistant across partner catalogs.",
    version="0.1.0",
    lifespan=lifespan,
)


@lru_cache
def _retriever() -> Retriever:
    """The shared retriever — built once (from config) so the model loads a single time."""
    return get_retriever()


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness probe: confirms the service process is up and serving."""
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
async def ready(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Readiness probe: confirms the service can reach its database.

    Liveness (above) only says the process is up; a platform like Cloud Run should
    route traffic only once dependencies are reachable, so this actually pings the DB.
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # surface as 503 so the platform holds traffic back
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unreachable"
        ) from exc
    return {"status": "ready"}


@app.get("/search", tags=["search"])
async def search(
    q: str = Query(..., min_length=1, description="The search query (German or English)."),
    top_k: int = Query(10, ge=1, le=50),
    partner: PartnerSlug | None = Query(None, description="Restrict to one partner."),
    sort: Sort = Query(Sort.RELEVANCE, description="Ordering among the relevant results."),
    require_tags: list[str] | None = Query(None, description="Keep only products with these tags."),
    session: AsyncSession = Depends(get_session),
) -> list[ProductOut]:
    """Search/recommend products across the partner catalogs.

    These are the explicit, mechanical capabilities the intent agent maps a natural-language
    query onto — filter to a partner, require tags, choose an ordering. The endpoint itself
    does not interpret intent.
    """
    hits = await _retriever().search(
        session, q, top_k=top_k, partner=partner, sort=sort, require_tags=require_tags
    )
    return [ProductOut.from_hit(h) for h in hits]


class AssistRequest(BaseModel):
    """A natural-language turn for the intent agent."""

    query: str = Field(..., min_length=1, description="The shopper's message (German or English).")


class ResumeRequest(BaseModel):
    """An answer to a clarifying question, tied to its paused conversation."""

    thread_id: str = Field(..., description="The thread_id returned by the clarify response.")
    answer: str = Field(..., min_length=1, description="The user's reply to the clarifying question.")


@app.post("/assist", tags=["assist"])
async def assist(
    body: AssistRequest,
    session: AsyncSession = Depends(get_session),
    agent=Depends(get_app_agent),
) -> AssistResponse:
    """Interpret a natural-language query and either recommend products or ask a question.

    The intent agent classifies the query, decides the next best action (search, clarify, or
    route to a partner), and returns a structured response. ``/search`` remains the mechanical
    primitive the agent drives; this endpoint is where intent is interpreted.
    """
    return await start_assist(agent, body.query, session)


@app.post("/assist/resume", tags=["assist"])
async def assist_resume(
    body: ResumeRequest,
    session: AsyncSession = Depends(get_session),
    agent=Depends(get_app_agent),
) -> AssistResponse:
    """Continue a conversation that paused to ask a clarifying question."""
    try:
        return await resume_assist(agent, body.thread_id, body.answer, session)
    except UnknownThreadError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No paused conversation for that thread_id (unknown or already finished).",
        ) from exc
