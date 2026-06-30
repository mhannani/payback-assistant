"""The closed set of retail partners the assistant searches across.

A single typed enum is the source of truth for partner identity, so 'dm' /
'edeka' / 'amazon' are never passed around as free-text strings that a typo
could break. Used by the data pipeline, the ORM, the retriever, and the API.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import quote_plus


class PartnerSlug(StrEnum):
    DM = "dm"
    EDEKA = "edeka"
    AMAZON = "amazon"


# Human-readable display names, kept next to the slugs they describe.
PARTNER_DISPLAY_NAMES: dict[PartnerSlug, str] = {
    PartnerSlug.DM: "dm-drogerie markt",
    PartnerSlug.EDEKA: "EDEKA",
    PartnerSlug.AMAZON: "Amazon",
}

# Each partner's own product-search URL, with a ``{q}`` placeholder for the query. Used for the
# agent's "navigational" action: when a shopper wants a specific shop, the assistant hands off
# to that partner's native search rather than answering from our catalog. These are the public
# German search endpoints; the deep-link is built by URL-encoding the query into the template.
PARTNER_SEARCH_URLS: dict[PartnerSlug, str] = {
    PartnerSlug.DM: "https://www.dm.de/search?query={q}",
    PartnerSlug.EDEKA: "https://www.edeka.de/unsere-marken/produkte/index/?query={q}",
    PartnerSlug.AMAZON: "https://www.amazon.de/s?k={q}",
}


def partner_search_url(partner: PartnerSlug, query: str) -> str:
    """Build a deep-link into ``partner``'s own search for ``query`` (URL-encoded)."""
    return PARTNER_SEARCH_URLS[partner].format(q=quote_plus(query))


@dataclass(frozen=True, slots=True)
class PartnerContact:
    """A partner's real customer-service contact — what the support hand-off points the user to.

    The assistant has no order/returns data of its own, so a ``customer_support`` query is answered
    by handing the shopper to the *partner's* own service desk. These are the public German contact
    details; the hand-off message (built in the agent runner) composes them into one helpful line.
    """

    phone: str  # the free German service hotline
    hours: str | None  # when that hotline is staffed (None = not publicly stated)
    email: str | None  # a general service inbox, when offered
    extra: str | None  # one extra channel worth mentioning (chat, callback, contact form)


# Each partner's real service contact. Keyed by slug like PARTNER_SEARCH_URLS, so partner reference
# data has one home. German details (the reviewers and customers are German); update here, not in the
# message builder. Sources: the partners' own service pages.
PARTNER_CONTACTS: dict[PartnerSlug, PartnerContact] = {
    PartnerSlug.DM: PartnerContact(
        phone="0800 3658633",
        hours="Mo–Sa 8–20 Uhr",
        email="ServiceCenter@dm.de",
        extra="Kontaktformular auf dm.de",
    ),
    PartnerSlug.EDEKA: PartnerContact(
        phone="0800 3335211",
        hours=None,
        email=None,
        extra="Kontaktformular auf edeka.de",
    ),
    PartnerSlug.AMAZON: PartnerContact(
        phone="0800 3638469",
        hours="täglich 6–24 Uhr",
        email=None,
        extra="Live-Chat und Rückruf-Service auf amazon.de",
    ),
}


def partner_contact(partner: PartnerSlug) -> PartnerContact:
    """The customer-service contact for ``partner`` (every partner is populated)."""
    return PARTNER_CONTACTS[partner]
