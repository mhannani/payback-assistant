"""EDEKA (grocery) adapter.

EDEKA's feed uses a German decimal-comma price string ("5,06"), a weight like
"700 g", and Open Food Facts label tags. This maps that shape into the canonical
product record.
"""

from __future__ import annotations

from app.shared.partner import PartnerSlug
from data.adapters.base import PartnerAdapter
from data.adapters.normalize import (
    compose_description,
    german_price_to_cents,
    normalize_tags,
    parse_quantity,
)
from data.schema import ProductRecord, RawRecord


class EdekaAdapter(PartnerAdapter):
    partner = PartnerSlug.EDEKA

    def to_canonical(self, raw: RawRecord) -> ProductRecord:
        name = raw["name"]
        brand = raw.get("hersteller") or None
        category = raw.get("kategorie") or None
        weight_g, volume_ml = parse_quantity(raw.get("weight"))

        attrs: dict = {"source_id": raw.get("ean"), "search_term": raw.get("suchwort")}
        if category:
            attrs["category"] = category

        return ProductRecord(
            partner=self.partner,
            brand=brand,
            name=name[:255],
            description=compose_description(brand, name, category, raw.get("weight")),
            price_cents=german_price_to_cents(raw["price"]),
            currency="EUR",
            image_url=raw.get("img"),
            tags=normalize_tags(raw.get("labels_tags")),
            weight_g=weight_g,
            volume_ml=volume_ml,
            attrs=attrs,
        )
