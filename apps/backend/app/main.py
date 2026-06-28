"""Application entrypoint: the FastAPI app and its top-level routes."""

from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.retrieval.base import Retriever
from app.retrieval.factory import get_retriever
from app.retrieval.types import Sort
from app.schemas import ProductOut
from app.shared.partner import PartnerSlug

app = FastAPI(
    title="PAYBACK Assistant",
    summary="Multilingual product assistant across partner catalogs.",
    version="0.1.0",
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
