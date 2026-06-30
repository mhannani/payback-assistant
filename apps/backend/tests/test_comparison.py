"""Hermetic tests for the comparison feature — the unit-price math and the compare graph node.

A comparison query answers with a *value* comparison: products ranked by price-per-unit (cheapest
value first, not cheapest sticker), each carrying a normalized unit price, with the best pick
highlighted. These cover the pure unit-price helper and the compare node's control flow with no LLM or
DB. The end-to-end LLM flow ("vergleiche die günstigsten Nudeln" → compare response) lives in the
key-gated test_assist_api.py.
"""

from __future__ import annotations

import uuid

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent import chains, graph
from app.agent.classification import Classification
from app.agent.graph import compile_agent
from app.agent.intents import Intent, Language, NextBestAction
from app.retrieval.ranking._common import price_per_unit, unit_price_from_hit
from app.retrieval.types import Candidate, SearchHit, Sort
from app.shared.partner import PartnerSlug


def _hit(*, price_cents: int, weight_g: int | None = None, volume_ml: int | None = None) -> SearchHit:
    return SearchHit(
        product_id=uuid.uuid4(),
        partner=PartnerSlug.EDEKA,
        name="x",
        brand=None,
        description=None,
        price_cents=price_cents,
        currency="EUR",
        image_url=None,
        tags=[],
        weight_g=weight_g,
        volume_ml=volume_ml,
        score=1.0,
    )


# ── unit_price_from_hit: the display unit price ──────────────────────


def test_unit_price_by_weight() -> None:
    # 200 ct for 400 g → 50 ct per 100 g.
    assert unit_price_from_hit(_hit(price_cents=200, weight_g=400)) == ("per_100g", 50)


def test_unit_price_by_volume() -> None:
    # 400 ct for 1000 ml → 40 ct per 100 ml.
    assert unit_price_from_hit(_hit(price_cents=400, volume_ml=1000)) == ("per_100ml", 40)


def test_unit_price_none_when_no_size() -> None:
    # A unitless item (e.g. a Kindle) has no meaningful unit price.
    assert unit_price_from_hit(_hit(price_cents=9900)) is None


def test_unit_price_agrees_with_ranker_formula() -> None:
    # The display helper and the ranker's price_per_unit must agree on value (one source of truth).
    hit = _hit(price_cents=250, weight_g=500)
    cand = Candidate(
        product_id=hit.product_id,
        partner=hit.partner,
        fused_score=1.0,
        price_cents=hit.price_cents,
        weight_g=hit.weight_g,
        volume_ml=hit.volume_ml,
    )
    _, ranker_value = price_per_unit(cand)
    basis, display_cents = unit_price_from_hit(hit)
    assert display_cents == round(ranker_value)
    assert basis == "per_100g"


# ── compare node: value-ranked, ends clean ───────────────────────────


class _ComparisonChain:
    """A classifier stand-in that always returns a COMPARISON classification."""

    async def ainvoke(self, _inputs: dict) -> Classification:
        return Classification(
            intent=Intent.COMPARISON,
            language=Language.DE,
            needs_clarification=False,
            clarification_question=None,
            partner=None,
            sort=Sort.RELEVANCE,  # deliberately NOT price_low — compare must force it anyway
            require_tags=[],
            search_query="Nudeln",
            message="Hier die Optionen nach Preis pro Menge, günstigste zuerst.",
        )


class _Retriever:
    def __init__(self, hits: list, expected_sort: Sort | None = None):
        self._hits = hits
        self._expected_sort = expected_sort
        self.seen_sort: Sort | None = None

    async def search(self, _query, *, sort=Sort.RELEVANCE, **_kwargs) -> list:
        self.seen_sort = sort
        return self._hits


async def test_comparison_forces_price_low_and_ends_with_hits(monkeypatch) -> None:
    chains.classifier_chain.cache_clear()
    monkeypatch.setattr(graph, "classifier_chain", lambda: _ComparisonChain())
    cheap = _hit(price_cents=100, weight_g=500)  # 20 ct/100g
    pricey = _hit(price_cents=300, weight_g=500)  # 60 ct/100g
    retriever = _Retriever([cheap, pricey])
    monkeypatch.setattr(graph, "get_cached_retriever", lambda: retriever)

    agent = compile_agent(MemorySaver())
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    result = await agent.ainvoke({"messages": [HumanMessage(content="welche Nudeln günstig?")]}, config)
    chains.classifier_chain.cache_clear()

    # The compare node forced PRICE_LOW even though the classification said RELEVANCE.
    assert retriever.seen_sort is Sort.PRICE_LOW
    assert result["action"] is NextBestAction.COMPARE
    assert not result.get("__interrupt__")
    assert len(result["hits"]) == 2


async def test_comparison_with_no_hits_ends_clean(monkeypatch) -> None:
    chains.classifier_chain.cache_clear()
    monkeypatch.setattr(graph, "classifier_chain", lambda: _ComparisonChain())
    monkeypatch.setattr(graph, "get_cached_retriever", lambda: _Retriever([]))

    agent = compile_agent(MemorySaver())
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    result = await agent.ainvoke({"messages": [HumanMessage(content="vergleiche xyz")]}, config)
    chains.classifier_chain.cache_clear()

    # Explicit comparison with nothing to compare ENDS — no clarify redirect, no interrupt.
    assert not result.get("__interrupt__")
    assert result["hits"] == []
    assert result["action"] is NextBestAction.COMPARE
