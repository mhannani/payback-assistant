"""The closed set of retail partners the assistant searches across.

A single typed enum is the source of truth for partner identity, so 'dm' /
'edeka' / 'amazon' are never passed around as free-text strings that a typo
could break. Used by the data pipeline, the ORM, the retriever, and the API.
"""

from __future__ import annotations

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
