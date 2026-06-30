"""Application entrypoint: the FastAPI app and its top-level routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.checkpointer import checkpointer_pool
from app.agent.graph import compile_agent
from app.agent.runner import UnknownThreadError, resume_assist, start_assist
from app.config import get_settings
from app.db.session import get_session
from app.retrieval.base import Retriever
from app.retrieval.base import backend_capabilities
from app.retrieval.factory import get_cached_retriever
from app.retrieval.types import Sort
from app.products import router as products_router
from app.schemas import AssistResponse, ProductOut
from app.shared.partner import PartnerSlug
from app.voice import router as voice_router


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

# The embeddable widget is served from a different origin than the API, so the browser's /assist
# calls are cross-origin and need CORS. (CORS does not cover WebSockets — the dictate socket guards
# itself.) credentials stay off: the widget sends no cookies, only JSON.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The widget mic's Deepgram-proxy WebSocket.
app.include_router(voice_router)
# The catalog browse endpoint (the products table page).
app.include_router(products_router)


def _retriever() -> Retriever:
    """The shared, process-cached retriever (see retrieval.factory.get_cached_retriever)."""
    return get_cached_retriever()


@app.get("/", tags=["ops"])
def root() -> dict[str, object]:
    """A friendly landing response that maps the API, so hitting the bare URL isn't a 404."""
    return {
        "name": "PAYBACK Assistant",
        "description": "Multilingual product assistant across partner catalogs (dm · EDEKA · Amazon).",
        "docs": "/docs",
        "endpoints": {
            "POST /assist": "Natural-language query → recommended products, a clarifying question, or a partner hand-off",
            "POST /assist/resume": "Answer a clarifying question and continue the same conversation",
            "GET /search?q=...": "Search all partner catalogs directly (the retrieval primitive the agent drives)",
            "GET /config": "The active, non-secret configuration (embedder, model, dimension, filter, ranker)",
            "GET /health": "Liveness probe — the process is up",
            "GET /ready": "Readiness probe — the database is reachable",
        },
    }


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


@app.get("/config", tags=["ops"])
def config() -> dict[str, object]:
    """The active (non-secret) configuration — the pluggable strategy stack at a glance.

    Useful when switching providers or A/B-testing strategies: you can see which embedder, model,
    dimension, filter, and ranker are live without reading env. Never exposes keys or DB creds.
    """
    s = get_settings()
    return {
        "embeddings": {
            "provider": s.embedding_provider,
            "model": s.openai_model if s.embedding_provider == "openai" else s.vertex_model,
            "dimension": s.embedding_dim,
        },
        "agent": {"llm_model": s.llm_model},
        "retrieval": {
            "backend": s.retriever_backend,
            # The arms this backend runs — pgvector is hybrid (vector+fulltext); a warehouse
            # backend may be vector-only. Surfaced so the difference is visible, not hidden.
            "capabilities": sorted(c.value for c in backend_capabilities(s.retriever_backend)),
            "filter_strategy": s.filter_strategy,
            "filter_ceiling": s.filter_ceiling,
            "ranking_strategy": s.ranking_strategy,
        },
    }


@app.get("/search", tags=["search"])
async def search(
    q: str = Query(..., min_length=1, description="The search query (German or English)."),
    top_k: int = Query(10, ge=1, le=50),
    partner: PartnerSlug | None = Query(None, description="Restrict to one partner."),
    sort: Sort = Query(Sort.RELEVANCE, description="Ordering among the relevant results."),
    require_tags: list[str] | None = Query(None, description="Keep only products with these tags."),
) -> list[ProductOut]:
    """Search/recommend products across the partner catalogs.

    These are the explicit, mechanical capabilities the intent agent maps a natural-language
    query onto — filter to a partner, require tags, choose an ordering. The endpoint itself
    does not interpret intent. The retriever owns its own data access, so no session is passed.
    """
    hits = await _retriever().search(
        q, top_k=top_k, partner=partner, sort=sort, require_tags=require_tags
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
    agent=Depends(get_app_agent),
) -> AssistResponse:
    """Interpret a natural-language query and either recommend products or ask a question.

    The intent agent classifies the query, decides the next best action (search, clarify, or
    route to a partner), and returns a structured response. ``/search`` remains the mechanical
    primitive the agent drives; this endpoint is where intent is interpreted.
    """
    return await start_assist(agent, body.query)


@app.post("/assist/resume", tags=["assist"])
async def assist_resume(
    body: ResumeRequest,
    agent=Depends(get_app_agent),
) -> AssistResponse:
    """Continue a conversation that paused to ask a clarifying question."""
    try:
        return await resume_assist(agent, body.thread_id, body.answer)
    except UnknownThreadError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No paused conversation for that thread_id (unknown or already finished).",
        ) from exc
