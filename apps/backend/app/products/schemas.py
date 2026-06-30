"""Schemas for the products catalog endpoint (the browse/table surface, distinct from /search).

``ProductRow`` is the list DTO — the same shape the dashboard table renders. ``ProductPage`` is the
server-side-pagination envelope (items + total + page info), so the table can show "page N of M"
without fetching the whole catalog.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.shared.partner import PartnerSlug


class ProductRow(BaseModel):
    """One catalog row for the products table."""

    model_config = ConfigDict(from_attributes=True)

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
    weight_g: int | None
    volume_ml: int | None


class ProductPage(BaseModel):
    """A page of catalog rows plus the totals the table's pager needs."""

    items: list[ProductRow]
    total: int  # total rows matching the filters (across all pages)
    page: int  # 1-based current page
    page_size: int
