"""End-to-end tests for the intent-agent endpoints (/assist, /assist/resume).

These exercise the real agent — LLM classification, the graph, the retriever, and the durable
checkpointer — so they are gated on the configured provider's credential (``requires_provider``)
and skipped without it. The agent's deterministic logic (intent→action policy, deep-link building)
is covered hermetically in test_agent_logic.py and always runs.
"""

from __future__ import annotations

import pytest

from tests.conftest import requires_provider

pytestmark = requires_provider


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


async def test_multi_turn_clarify_converges_to_products(agent_client) -> None:
    # The live bug, end-to-end: a vague opener answered over SEVERAL partial turns must eventually
    # return products — the conversation accumulates (add_messages), so once the answers name a
    # concrete product in the catalog the agent stops clarifying and searches. The product chosen
    # ("pasta dinner") exists in all-partner seed data and mirrors the brief's own example query.
    first = await agent_client.post("/assist", json={"query": "I want something to eat"})
    assert first.status_code == 200
    body = first.json()
    assert body["type"] == "clarify"
    thread_id = body["thread_id"]

    # Feed progressively more specific answers; the agent must converge to products within the
    # clarification budget rather than asking forever.
    for answer in ("italian", "pasta for dinner"):
        resumed = await agent_client.post(
            "/assist/resume", json={"thread_id": thread_id, "answer": answer}
        )
        assert resumed.status_code == 200
        body = resumed.json()
        if body["type"] == "products":
            break

    assert body["type"] == "products", "agent kept clarifying instead of converging to products"
    assert len(body["items"]) > 0


async def test_resume_unknown_thread_is_404(agent_client) -> None:
    resp = await agent_client.post(
        "/assist/resume", json={"thread_id": "does-not-exist", "answer": "x"}
    )
    assert resp.status_code == 404


async def test_comparison_query_returns_value_comparison(agent_client) -> None:
    # A comparison query answers with a value comparison: items ranked by price-per-unit, a best pick,
    # and unit prices on the items. "Nudeln" exists across partners with weights, so €/100g is real.
    resp = await agent_client.post(
        "/assist", json={"query": "vergleiche die günstigsten Nudeln"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "compare"
    assert len(body["items"]) > 0
    assert body["cheapest_pick"] is not None
    # At least one item carries a normalized unit price (the comparison metric).
    assert any(p["unit_price_cents"] is not None for p in body["items"])


async def test_off_topic_query_is_declined(agent_client) -> None:
    # A non-shopping request (write code) must be politely refused, not searched or clarified.
    resp = await agent_client.post("/assist", json={"query": "Schreib mir ein Python-Skript"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "decline"
    assert body["message"]
    assert "items" not in body  # not a product answer


async def test_support_query_hands_off_to_partner(agent_client) -> None:
    # An orders/returns question naming a shop hands the shopper to that shop's real service desk.
    resp = await agent_client.post(
        "/assist", json={"query": "Wo ist meine Bestellung bei EDEKA?"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "decline"
    assert "0800 3335211" in body["message"]  # EDEKA's real customer-service number


@pytest.mark.parametrize("body", [{}, {"query": ""}])
async def test_assist_rejects_invalid_body(agent_client, body) -> None:
    resp = await agent_client.post("/assist", json=body)
    assert resp.status_code == 422


async def test_assist_rejects_oversized_query(agent_client) -> None:
    # Cheap input guardrail: an abnormally long body is rejected at the schema (422) before any
    # model call is spent — caps an injection/DoS vector. A real shopper turn is never this long.
    resp = await agent_client.post("/assist", json={"query": "a" * 3000})
    assert resp.status_code == 422
