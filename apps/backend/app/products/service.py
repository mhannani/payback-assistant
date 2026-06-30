"""Catalog browse service — list/filter/sort/paginate products for the table page.

This is the *mechanical* browse surface, separate from `/search` (which is semantic retrieval). It
builds plain SQL: optional partner/tag/search filters become WHERE clauses, a sort choice becomes
ORDER BY, and the page window is a SQL LIMIT/OFFSET — all server-side, with a COUNT for the total so
the table can paginate without fetching the whole catalog. Mirrors Helfio's clients list pattern.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Brand, Product
from app.products.schemas import ProductPage, ProductRow
from app.shared.partner import PartnerSlug


class ProductSort(StrEnum):
    """How to order the catalog table. Distinct from retrieval's relevance ``Sort``."""

    NAME = "name"
    PRICE_LOW = "price_low"
    PRICE_HIGH = "price_high"


class ProductCatalogService:
    """Lists catalog rows with server-side filtering, sorting, and pagination."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_products(
        self,
        *,
        search: str | None = None,
        partner: PartnerSlug | None = None,
        tags: Sequence[str] | None = None,
        sort: ProductSort = ProductSort.NAME,
        page: int = 1,
        page_size: int = 24,
    ) -> ProductPage:
        # Base filter set (shared by the count and the page query) — partner, required tags, and a
        # case-insensitive search over name + brand.
        conditions = []
        if partner is not None:
            conditions.append(Product.partner.has(slug=partner.value))
        if tags:
            # array-contains-all (@>), served by the GIN index on tags; cast to text[] to match.
            conditions.append(Product.tags.contains(cast(list(tags), ARRAY(Text))))
        if search:
            like = f"%{search.lower()}%"
            conditions.append(
                or_(
                    func.lower(Product.name).like(like),
                    Product.brand.has(func.lower(Brand.name).like(like)),
                )
            )

        # Total matching rows (for the pager), before the LIMIT/OFFSET window.
        count_stmt = select(func.count(Product.id))
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
        total = int((await self._session.scalar(count_stmt)) or 0)

        # The page window: eager-load partner + brand (rendered per row), sorted, sliced.
        stmt = select(Product).options(selectinload(Product.partner), selectinload(Product.brand))
        for cond in conditions:
            stmt = stmt.where(cond)
        stmt = _apply_sort(stmt, sort)
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        products = (await self._session.scalars(stmt)).all()
        items = [
            ProductRow(
                id=p.id,
                partner=PartnerSlug(p.partner.slug),
                partner_name=p.partner.name,
                name=p.name,
                brand=p.brand.name if p.brand else None,
                description=p.description,
                price_cents=p.price_cents,
                currency=p.currency,
                image_url=p.image_url,
                tags=list(p.tags),
                weight_g=p.weight_g,
                volume_ml=p.volume_ml,
            )
            for p in products
        ]
        return ProductPage(items=items, total=total, page=page, page_size=page_size)


def _apply_sort(stmt, sort: ProductSort):
    """Add the ORDER BY for the chosen sort. Name is the default browse order."""
    match sort:
        case ProductSort.PRICE_LOW:
            return stmt.order_by(Product.price_cents.asc(), Product.name.asc())
        case ProductSort.PRICE_HIGH:
            return stmt.order_by(Product.price_cents.desc(), Product.name.asc())
        case _:
            return stmt.order_by(Product.name.asc())
