"""Hermetic unit tests for the agent's deterministic logic — no LLM, always run.

These cover the parts of the agent that are pure functions of their input: the intent→action
policy, the partner deep-link builder, and the response union. They need no model or network,
so they run in every environment (unlike the LLM-driven flow tests, which are key-gated).
"""

from __future__ import annotations

import pytest

from app.agent.classification import Classification
from app.agent.intents import Intent, Language, NextBestAction
from app.agent.state import decide_action
from app.retrieval.types import Sort
from app.shared.partner import PartnerSlug, partner_search_url


def _classification(**overrides) -> Classification:
    base = dict(
        intent=Intent.SEARCH,
        language=Language.DE,
        needs_clarification=False,
        clarification_question=None,
        partner=None,
        sort=Sort.RELEVANCE,
        require_tags=[],
        search_query="Windeln",
    )
    base.update(overrides)
    return Classification(**base)


# ── decide_action: the intent → next-best-action policy ──────────────


def test_specific_query_searches() -> None:
    assert decide_action(_classification()) is NextBestAction.SEARCH


def test_named_partner_routes() -> None:
    c = _classification(partner=PartnerSlug.DM)
    assert decide_action(c) is NextBestAction.ROUTE_TO_PARTNER


def test_vague_query_clarifies() -> None:
    c = _classification(intent=Intent.DISCOVERY, needs_clarification=True)
    assert decide_action(c) is NextBestAction.CLARIFY


def test_customer_support_declines() -> None:
    # Orders/returns aren't catalog searches and we have no order data — hand off, don't clarify.
    assert decide_action(_classification(intent=Intent.CUSTOMER_SUPPORT)) is NextBestAction.DECLINE


def test_off_topic_declines() -> None:
    # Not about shopping at all (code, weather, chit-chat) → a polite refusal, never a search/clarify.
    assert decide_action(_classification(intent=Intent.OFF_TOPIC)) is NextBestAction.DECLINE


def test_decline_wins_over_partner_and_clarify() -> None:
    # Even if the model also guessed a partner or set needs_clarification, an out-of-scope intent
    # declines first — we never route or clarify an off-topic / support query.
    c = _classification(
        intent=Intent.OFF_TOPIC, needs_clarification=True, partner=PartnerSlug.DM
    )
    assert decide_action(c) is NextBestAction.DECLINE


def test_clarify_wins_over_route_when_vague() -> None:
    # Regression: the model may set a partner on a vague query; clarify must still win, or we'd
    # route a meaningless search and return an empty list.
    c = _classification(
        intent=Intent.DISCOVERY, needs_clarification=True, partner=PartnerSlug.DM
    )
    assert decide_action(c) is NextBestAction.CLARIFY


# ── partner_search_url: the deep-link handoff ────────────────────────


@pytest.mark.parametrize("partner", list(PartnerSlug))
def test_partner_search_url_is_built_for_every_partner(partner: PartnerSlug) -> None:
    url = partner_search_url(partner, "Bio Nudeln")
    assert url.startswith("https://")
    assert "Bio" in url and "Nudeln" in url  # the query is present (URL-encoded)
    assert " " not in url  # spaces are encoded, never raw


def test_partner_search_url_encodes_special_chars() -> None:
    # German umlauts / spaces must be percent-encoded so the link is valid.
    url = partner_search_url(PartnerSlug.EDEKA, "Erdnüsse & Co")
    assert " " not in url
    assert "&" not in url.split("?", 1)[1].split("=", 1)[1]  # the query value has no raw '&'
