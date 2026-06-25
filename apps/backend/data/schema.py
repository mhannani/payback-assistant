"""Shared shape for a catalog record.

The canonical record every partner adapter produces and the seeder consumes — one
contract for all three partners.
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.shared.partner import PartnerSlug

# Each partner's source feed has its own shape (different field names, units, and
# extras). A raw record is just that untyped per-partner dict; the partner's
# adapter turns it into the canonical ``ProductRecord`` below.
RawRecord = dict[str, Any]


class ProductRecord(TypedDict):
    partner: PartnerSlug
    brand: str | None
    name: str
    description: str
    price_cents: int
    currency: str
    image_url: str | None
    # Canonical dietary/label tags (e.g. ['organic', 'vegan']) for filtering.
    tags: list[str]
    # Size normalized to base units (one set when the source quantity parses).
    weight_g: int | None
    volume_ml: int | None
    # Rare partner-specific extras not filtered/ranked on (source id, rating…).
    attrs: dict[str, Any]
