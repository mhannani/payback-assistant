"""Application entrypoint: the FastAPI app and its top-level routes."""

from fastapi import FastAPI

app = FastAPI(
    title="PAYBACK Assistant",
    summary="Multilingual product assistant across partner catalogs.",
    version="0.1.0",
)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness probe: confirms the service process is up and serving."""
    return {"status": "ok"}
