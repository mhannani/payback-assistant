"""Amazon (long-tail merchandise) adapter.

Amazon's feed uses a float ``list_price``, a star ``rating``, an ``asin``, and a
``category_path`` breadcrumb. General merchandise carries no dietary labels, so
``tags`` is empty. This maps that shape into the canonical product record.
"""

from __future__ import annotations

from app.shared.partner import PartnerSlug
from data.adapters.base import PartnerAdapter
from data.adapters.normalize import euros_to_cents
from data.schema import ProductRecord, RawRecord


class AmazonAdapter(PartnerAdapter):
    partner = PartnerSlug.AMAZON

    def to_canonical(self, raw: RawRecord) -> ProductRecord:
        name = raw["product_name"]
        brand = raw.get("brand") or None
        blurb = raw.get("blurb") or None
        category_path = raw.get("category_path") or None

        attrs: dict = {"source_id": raw.get("asin"), "category_path": category_path}
        if raw.get("rating") is not None:
            attrs["rating"] = raw["rating"]

        return ProductRecord(
            partner=self.partner,
            brand=brand,
            name=name[:255],
            description=_describe(brand, name, blurb, category_path),
            # Catalog prices are quoted in EUR for this project; list_price is a plain amount.
            price_cents=euros_to_cents(raw["list_price"]),
            currency="EUR",
            image_url=raw.get("image"),
            tags=[],
            weight_g=None,
            volume_ml=None,
            attrs=attrs,
        )


def _describe(brand: str | None, name: str, blurb: str | None, category_path: str | None) -> str:
    parts = [p for p in (brand, name, blurb, category_path) if p]
    return ". ".join(parts) + "."
