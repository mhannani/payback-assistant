"""API response models.

These are the JSON shapes the API returns — kept separate from the internal retrieval
types (``SearchHit``) so the wire contract can evolve independently of the internals.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.retrieval.types import SearchHit
from app.shared.partner import PARTNER_DISPLAY_NAMES, PartnerSlug


class ProductOut(BaseModel):
    """One recommended product in a search response.

    Result *position* is the ranking signal: the list is already ordered by the chosen
    strategy (relevance, then cross-partner fairness, then the requested sort). The raw
    fused relevance score is deliberately not exposed — fairness re-ordering makes it
    non-monotonic with position, so returning it would only invite "why is this out of
    order?" Order is the contract; the internal score stays internal (``SearchHit.score``).
    """

    id: uuid.UUID
    partner: PartnerSlug
    partner_name: str
    name: str
    brand: str | None
    description: str | None
    price_cents: int
    currency: str
    image_url: str | None
    tags: list[str]

    @classmethod
    def from_hit(cls, hit: SearchHit) -> ProductOut:
        return cls(
            id=hit.product_id,
            partner=hit.partner,
            partner_name=PARTNER_DISPLAY_NAMES[hit.partner],
            name=hit.name,
            brand=hit.brand,
            description=hit.description,
            price_cents=hit.price_cents,
            currency=hit.currency,
            image_url=hit.image_url,
            tags=hit.tags,
        )
