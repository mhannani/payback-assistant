"""Hermetic tests for the out-of-scope hand-off — the support / off-topic decline messages.

The assistant answers an out-of-scope query (orders/returns, or anything not about shopping) with a
helpful text reply, not a product search. These cover the pure message builder and the partner
contact registry, so they need no LLM or DB and always run. The end-to-end routing (a real query →
a decline response) is exercised in the key-gated test_assist_api.py.
"""

from __future__ import annotations

import pytest

from app.agent.classification import Classification
from app.agent.intents import Intent, Language
from app.agent.runner import _decline_message
from app.retrieval.types import Sort
from app.shared.partner import PARTNER_CONTACTS, PartnerSlug


def _classification(**overrides) -> Classification:
    base = dict(
        intent=Intent.CUSTOMER_SUPPORT,
        language=Language.DE,
        needs_clarification=False,
        clarification_question=None,
        partner=None,
        sort=Sort.RELEVANCE,
        require_tags=[],
        search_query="",
        message=None,
    )
    base.update(overrides)
    return Classification(**base)


def test_every_partner_has_real_contact_data() -> None:
    # All three partners are populated — none falls back to the generic message on a named support
    # query. Each contact has at least a phone number.
    assert set(PARTNER_CONTACTS) == set(PartnerSlug)
    for contact in PARTNER_CONTACTS.values():
        assert contact.phone


@pytest.mark.parametrize(
    "partner, expected_phone",
    [
        (PartnerSlug.EDEKA, "0800 3335211"),
        (PartnerSlug.DM, "0800 3658633"),
        (PartnerSlug.AMAZON, "0800 3638469"),
    ],
)
def test_support_handoff_quotes_named_partner_contact(partner, expected_phone) -> None:
    # A support query that named a shop hands the shopper to THAT shop's real service desk.
    msg = _decline_message(_classification(intent=Intent.CUSTOMER_SUPPORT, partner=partner))
    assert expected_phone in msg
    assert "Bestellungen" in msg  # framed as an orders/returns hand-off


def test_support_handoff_is_formal_sie_not_du() -> None:
    # German copy addresses the customer formally — "Ihnen"/"Sie", never "du"/"dich"/"dein".
    msg = _decline_message(
        _classification(intent=Intent.CUSTOMER_SUPPORT, partner=PartnerSlug.EDEKA)
    )
    lowered = f" {msg.lower()} "
    assert "ihnen" in msg.lower()
    for informal in (" du ", " dich ", " dein ", " deine "):
        assert informal not in lowered


def test_support_without_partner_is_generic_handoff() -> None:
    # No shop named → a general "contact the retailer" hand-off, still offering product help.
    msg = _decline_message(_classification(intent=Intent.CUSTOMER_SUPPORT, partner=None))
    assert "Kundenservice" in msg
    assert "Produktsuche" in msg  # still invites the in-scope use


def test_off_topic_declines_politely() -> None:
    # Out of scope entirely (coding, weather, chit-chat) → a short product-only refusal.
    de = _decline_message(_classification(intent=Intent.OFF_TOPIC, language=Language.DE))
    assert "Produktsuche" in de
    en = _decline_message(_classification(intent=Intent.OFF_TOPIC, language=Language.EN))
    assert "product searches" in en
