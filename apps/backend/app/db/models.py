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
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Embedding dimensionality. Kept in sync with Settings.embedding_dim; declared
# here too because a column needs a concrete size at class-definition time.
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

    Shared columns drive cross-partner search and ranking; ``attrs`` holds the
    partner-specific shape (e.g. dm: size_ml/category; EDEKA: unit/bio; Amazon:
    asin/category_path). ``embedding`` is the semantic vector; ``search_tsv`` is
    a generated full-text column (declared in init.sql) used for keyword search.
    """

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_partner", "partner_id"),
        Index("ix_products_brand", "brand_id"),
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


    # Partner-specific fields that don't fit the shared columns.
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Semantic embedding of name + description (set at seed time).
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    partner: Mapped[Partner] = relationship(back_populates="products")
    brand: Mapped[Brand | None] = relationship(back_populates="products")
