"""Load the committed catalog snapshots into Postgres.

Reads only the on-disk JSON (no network), so it is reproducible and runs fully
inside Docker. Idempotent: each run truncates the catalog and reloads it, so
re-seeding never duplicates rows. Embeddings are left NULL here and computed in
a dedicated step once the embedder is available.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.models import Brand, Partner, Product
from app.db.session import SessionFactory, engine
from app.shared.partner import PARTNER_DISPLAY_NAMES, PartnerSlug
from data.catalog_loader import load_all_catalogs


async def seed() -> int:
    """Truncate the catalog and load every partner's snapshot. Returns the count."""
    records = load_all_catalogs()

    async with SessionFactory() as session:
        # Clean slate — CASCADE clears brands + products with the partners.
        await session.execute(text("TRUNCATE partners, brands, products CASCADE"))

        # One Partner row per known slug.
        partners: dict[PartnerSlug, Partner] = {}
        for slug in PartnerSlug:
            partner = Partner(slug=slug.value, name=PARTNER_DISPLAY_NAMES[slug])
            session.add(partner)
            partners[slug] = partner
        await session.flush()  # assign partner ids

        # Deduplicate brands per (partner, brand name).
        brands: dict[tuple[PartnerSlug, str], Brand] = {}
        for rec in records:
            if not rec["brand"]:
                continue
            key = (rec["partner"], rec["brand"])
            if key not in brands:
                brand = Brand(partner_id=partners[rec["partner"]].id, name=rec["brand"])
                session.add(brand)
                brands[key] = brand
        await session.flush()  # assign brand ids

        for rec in records:
            brand = brands.get((rec["partner"], rec["brand"])) if rec["brand"] else None
            session.add(
                Product(
                    partner_id=partners[rec["partner"]].id,
                    brand_id=brand.id if brand else None,
                    name=rec["name"],
                    description=rec["description"],
                    price_cents=rec["price_cents"],
                    currency=rec["currency"],
                    image_url=rec["image_url"],
                    tags=rec["tags"],
                    weight_g=rec["weight_g"],
                    volume_ml=rec["volume_ml"],
                    attrs=rec["attrs"],
                )
            )

        await session.commit()
    return len(records)


async def _main() -> None:
    count = await seed()
    print(f"Seeded {count} products.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
