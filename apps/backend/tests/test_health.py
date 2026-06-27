"""Smoke tests for the ops endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready_when_db_reachable() -> None:
    # The test runs inside the container alongside the DB, so readiness should pass.
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
