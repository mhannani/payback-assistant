"""End-to-end tests for the intent-agent endpoints (/assist, /assist/resume).

These exercise the real agent — LLM classification, the graph, the retriever, and the durable
checkpointer — so they are gated on an OpenAI key (``requires_llm``) and skipped without one.
The agent's deterministic logic (intent→action policy, deep-link building) is covered
hermetically in test_agent_logic.py and always runs.
"""

from __future__ import annotations

import pytest

from tests.conftest import requires_llm

pytestmark = requires_llm


async def test_specific_query_returns_products(agent_client) -> None:
    resp = await agent_client.post("/assist", json={"query": "günstige Windeln"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "products"
    assert body["language"] == "de"
    assert len(body["items"]) > 0
    assert all("windel" in p["name"].lower() for p in body["items"][:3])


async def test_navigational_query_returns_route_handoff(agent_client) -> None:
    resp = await agent_client.post("/assist", json={"query": "zeig mir Kaffee bei edeka"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "route"
    assert body["partner"] == "edeka"
    assert "edeka" in body["deeplink"] and "Kaffee" in body["deeplink"]
    assert "items" not in body  # a hand-off, not catalog results


async def test_vague_query_clarifies_then_resumes(agent_client) -> None:
    # A query with no concrete product term should pause and ask.
    first = await agent_client.post("/assist", json={"query": "ich suche etwas"})
    assert first.status_code == 200
    clarify = first.json()
    assert clarify["type"] == "clarify"
    assert clarify["question"]
    thread_id = clarify["thread_id"]

    # Answering with a concrete product resumes the same thread and returns products.
    resumed = await agent_client.post(
        "/assist/resume", json={"thread_id": thread_id, "answer": "Schokolade"}
    )
    assert resumed.status_code == 200
    body = resumed.json()
    assert body["type"] == "products"
    assert any("schoko" in p["name"].lower() for p in body["items"])


async def test_resume_unknown_thread_is_404(agent_client) -> None:
    resp = await agent_client.post(
        "/assist/resume", json={"thread_id": "does-not-exist", "answer": "x"}
    )
    assert resp.status_code == 404


@pytest.mark.parametrize("body", [{}, {"query": ""}])
async def test_assist_rejects_invalid_body(agent_client, body) -> None:
    resp = await agent_client.post("/assist", json=body)
    assert resp.status_code == 422
