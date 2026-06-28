"""Smoke tests for the ops endpoints.

Uses the async ``api_client`` (httpx + ASGI) so requests share the suite's single event
loop — the sync TestClient spins its own loop per request and conflicts with it.
"""

from __future__ import annotations


async def test_health_returns_ok(api_client) -> None:
    response = await api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_returns_ready_when_db_reachable(api_client) -> None:
    # The test runs inside the container alongside the DB, so readiness should pass.
    response = await api_client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
