"""Row hydration shared by every retriever.

A retriever's candidate-generation arm yields product ids + a fused score; both the pgvector and the
BigQuery backends then need to turn those ids into ranking ``Candidate`` views and public
``SearchHit`` rows from the catalog. The catalog rows live in Postgres (the single source of truth)
regardless of which backend ran the vector search, so this loader is shared rather than duplicated.

Ids absent from Postgres are skipped: a vector index (e.g. BigQuery) can briefly disagree with the
row store during a re-embed, and a stale id must not crash a search.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Product
from app.retrieval.types import Candidate, SearchHit
from app.shared.partner import PartnerSlug


async def load_candidates(
    session: AsyncSession, fused: dict[uuid.UUID, float]
) -> tuple[list[Candidate], dict[uuid.UUID, Product]]:
    """Load the fused products once, eager-loading partner + brand.

    Eager-loading avoids a lazy relationship access later (which would attempt async IO outside the
    await context and fail). Returns the ranking ``Candidate`` views plus the full rows, keyed by id.
    """
    stmt = (
        select(Product)
        .where(Product.id.in_(fused.keys()))
        .options(selectinload(Product.partner), selectinload(Product.brand))
    )
    products = {p.id: p for p in (await session.scalars(stmt)).all()}
    candidates = [
        Candidate(
            product_id=p.id,
            partner=PartnerSlug(p.partner.slug),
            fused_score=fused[p.id],
            price_cents=p.price_cents,
            weight_g=p.weight_g,
            volume_ml=p.volume_ml,
        )
        for p in products.values()
    ]
    return candidates, products


def to_hit(product: Product, score: float) -> SearchHit:
    """Build the public ``SearchHit`` from a loaded product row and its final score."""
    return SearchHit(
        product_id=product.id,
        partner=PartnerSlug(product.partner.slug),
        name=product.name,
        brand=product.brand.name if product.brand else None,
        description=product.description,
        price_cents=product.price_cents,
        currency=product.currency,
        image_url=product.image_url,
        tags=list(product.tags),
        weight_g=product.weight_g,
        volume_ml=product.volume_ml,
        score=score,
        attrs=dict(product.attrs),
    )
