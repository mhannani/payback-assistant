"""Shared shape for a catalog record.

Both the Open Food Facts fetcher and the curated Amazon catalog emit records in
this shape, and the seeder consumes it — one contract for all three partners.
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.shared.partner import PartnerSlug


class ProductRecord(TypedDict):
    partner: PartnerSlug
    brand: str | None
    name: str
    description: str
    price_cents: int
    currency: str
    image_url: str | None
    attrs: dict[str, Any]
