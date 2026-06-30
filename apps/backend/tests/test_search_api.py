"""API tests for the /search endpoint (runs against the seeded + embedded catalog).

Uses the async ``api_client`` (httpx + ASGI) so the app's async engine stays on one event
loop — the sync TestClient spins a fresh loop per request and trips "event loop is closed".
"""

from __future__ import annotations

from tests.conftest import requires_provider

# The query tests embed the query through the configured provider, so they need its credential;
# the validation tests below (422 cases) don't touch the embedder and always run.


@requires_provider
async def test_search_returns_products_with_required_fields(api_client) -> None:
    resp = await api_client.get("/search", params={"q": "shampoo", "top_k": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body
    first = body[0]
    for field in ("id", "partner", "partner_name", "name", "price_cents", "currency", "tags"):
        assert field in first
    # The raw relevance score is intentionally not exposed — order is the ranking signal.
    assert "score" not in first


@requires_provider
async def test_search_partner_filter(api_client) -> None:
    resp = await api_client.get("/search", params={"q": "shampoo", "partner": "dm", "top_k": 5})
    assert resp.status_code == 200
    assert all(p["partner"] == "dm" for p in resp.json())


@requires_provider
async def test_search_top_k_is_honoured(api_client) -> None:
    resp = await api_client.get("/search", params={"q": "pasta dinner", "top_k": 3})
    assert resp.status_code == 200
    assert len(resp.json()) <= 3


async def test_search_requires_a_query(api_client) -> None:
    assert (await api_client.get("/search")).status_code == 422  # q is required


async def test_search_rejects_unknown_sort(api_client) -> None:
    resp = await api_client.get("/search", params={"q": "shampoo", "sort": "nonsense"})
    assert resp.status_code == 422  # not a valid Sort value
