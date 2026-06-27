"""Application entrypoint: the FastAPI app and its top-level routes."""

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

app = FastAPI(
    title="PAYBACK Assistant",
    summary="Multilingual product assistant across partner catalogs.",
    version="0.1.0",
)


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
