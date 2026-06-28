"""SQLAlchemy ORM models for the product catalog.

All three partners (dm, EDEKA, Amazon) share one ``Product`` table: the common,
queryable fields are real columns, while each partner's idiosyncratic fields
live in a JSONB ``attrs`` column. This lets a single query — and a single
vector index — search across otherwise heterogeneous catalogs, which is what
the assistant needs to recommend fairly across partners.

Columns use SQLAlchemy 2.0 typed ``Mapped[...]`` / ``mapped_column(...)`` so the
schema is statically checked end to end.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Embedding dimensionality. Must match VECTOR(N) in db/init.sql; the embedder factory
# (app/embeddings/factory.py) rejects any provider whose output dimension differs.
# Declared here too because a column needs a concrete size at class-definition time.
EMBEDDING_DIM = 384


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Partner(Base):
    """A retail partner whose catalog the assistant can search (e.g. dm)."""

    __tablename__ = "partners"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Stable slug used in API responses and routing ('dm' | 'edeka' | 'amazon').
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))

    products: Mapped[list[Product]] = relationship(back_populates="partner")
    brands: Mapped[list[Brand]] = relationship(back_populates="partner")


class Brand(Base):
    """A product brand, scoped to the partner that carries it."""

    __tablename__ = "brands"
    __table_args__ = (
        Index("ix_brands_partner_name", "partner_id", "name", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))

    partner: Mapped[Partner] = relationship(back_populates="brands")
    products: Mapped[list[Product]] = relationship(back_populates="brand")


class Product(Base):
    """A single catalog item.

    Shared columns drive cross-partner search and ranking. ``tags`` (organic, vegan…)
    and the normalized ``weight_g``/``volume_ml`` are extracted at ingestion so they are
    directly filterable/rankable without runtime parsing; rare partner-specific extras
    (source id, rating, category) live in ``attrs``. ``embedding`` is the semantic vector;
    ``search_tsv`` is a generated full-text column (declared in init.sql) for keyword search.
    """

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_partner", "partner_id"),
        Index("ix_products_brand", "brand_id"),
        Index("ix_products_tags_gin", "tags", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE")
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("brands.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    price_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    # Product image (referenced by URL, not stored). Populated from the source
    # catalog; surfaced by the assistant so a client can render product photos.
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Canonical dietary/label tags (e.g. 'organic', 'vegan'), GIN-indexed so the
    # agent can filter on an attribute with `WHERE 'organic' = ANY(tags)`.
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # Size normalized to base units at ingestion (one of these is set when the
    # source carries a parseable quantity), enabling price-per-unit ranking.
    weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volume_ml: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Rare partner-specific extras that aren't filtered/ranked on (source id, rating…).
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Semantic embedding of name + description (computed by `make embed`).
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
    # Which embedder produced `embedding` (e.g. 'local:paraphrase-multilingual-MiniLM-L12-v2').
    # Vectors from different models aren't comparable, so this lets the embed step
    # re-embed when the provider changes and lets retrieval reject a stale mismatch.
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # German full-text vector over name + description — the keyword arm of hybrid
    # search. Generated by the database (declared in init.sql), so it's read-only to
    # the ORM: FetchedValue marks it DB-maintained and excluded from INSERT/UPDATE.
    search_tsv: Mapped[str | None] = mapped_column(TSVECTOR, FetchedValue())

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    partner: Mapped[Partner] = relationship(back_populates="products")
    brand: Mapped[Brand | None] = relationship(back_populates="products")
