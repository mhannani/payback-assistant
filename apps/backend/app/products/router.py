"""The catalog browse endpoint — GET /products (list/filter/sort/paginate).

The table page calls this to render the catalog. Distinct from /search (semantic retrieval): this is
a plain, deterministic listing with explicit filters, server-side paginated.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.products.schemas import ProductPage
from app.products.service import ProductCatalogService, ProductSort
from app.shared.partner import PartnerSlug

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductPage)
async def list_products(
    search: str | None = Query(None, description="Case-insensitive search over name + brand."),
    partner: PartnerSlug | None = Query(None, description="Restrict to one partner."),
    tags: list[str] | None = Query(None, description="Keep only products carrying all these tags."),
    sort: ProductSort = Query(ProductSort.NAME, description="Row ordering."),
    page: int = Query(1, ge=1, description="1-based page number."),
    page_size: int = Query(24, ge=1, le=100, description="Rows per page."),
    session: AsyncSession = Depends(get_session),
) -> ProductPage:
    """List the catalog with server-side filtering, sorting, and pagination."""
    return await ProductCatalogService(session).list_products(
        search=search, partner=partner, tags=tags, sort=sort, page=page, page_size=page_size
    )
