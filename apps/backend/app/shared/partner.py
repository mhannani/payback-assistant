"""The closed set of retail partners the assistant searches across.

A single typed enum is the source of truth for partner identity, so 'dm' /
'edeka' / 'amazon' are never passed around as free-text strings that a typo
could break. Used by the data pipeline, the ORM, the retriever, and the API.
"""

from __future__ import annotations

from enum import StrEnum


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
