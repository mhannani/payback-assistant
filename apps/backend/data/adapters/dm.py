"""dm (drugstore) adapter.

dm's feed uses German field names, a euro float price, and a pack size like
"300 ml". This maps that shape into the canonical product record.
"""

from __future__ import annotations

from app.shared.partner import PartnerSlug
from data.adapters.base import PartnerAdapter
from data.adapters.normalize import (
    compose_description,
    euros_to_cents,
    normalize_tags,
    parse_quantity,
)
from data.schema import ProductRecord, RawRecord


class DmAdapter(PartnerAdapter):
    partner = PartnerSlug.DM

    def to_canonical(self, raw: RawRecord) -> ProductRecord:
        name = raw["title"]
        brand = raw.get("marke") or None
        category = raw.get("dm_category") or None
        weight_g, volume_ml = parse_quantity(raw.get("pack_size"))

        attrs: dict = {"source_id": raw.get("dm_gtin"), "search_term": raw.get("quelle_suchbegriff")}
        if category:
            attrs["category"] = category

        return ProductRecord(
            partner=self.partner,
            brand=brand,
            name=name[:255],
            description=compose_description(brand, name, category, raw.get("pack_size")),
            price_cents=euros_to_cents(raw["price_eur"]),
            currency="EUR",
            image_url=raw.get("bild_url"),
            tags=normalize_tags(raw.get("labels_tags")),
            weight_g=weight_g,
            volume_ml=volume_ml,
            attrs=attrs,
        )
