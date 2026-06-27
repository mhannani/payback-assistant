"""DB-backed tests for the embed step (real Postgres + pgvector via db_session)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models import EMBEDDING_DIM, Partner, Product
from data.embed import embed_outdated


async def _make_product(session, *, embedding=None, embedding_model=None) -> Product:
    """Insert a partner + one product into the rolled-back test transaction."""
    partner = Partner(slug=f"t-{uuid.uuid4().hex[:8]}", name="Test")
    session.add(partner)
    await session.flush()
    product = Product(
        partner_id=partner.id,
        name="Bio Vollkorn Spaghetti",
        description="organic wholegrain pasta",
        price_cents=199,
        currency="EUR",
        embedding=embedding,
        embedding_model=embedding_model,
    )
    session.add(product)
    await session.flush()
    return product


async def test_embed_fills_null_embeddings(db_session, embedder) -> None:
    product = await _make_product(db_session)
    assert product.embedding is None

    count = await embed_outdated(db_session, embedder)

    assert count >= 1
    refreshed = await db_session.get(Product, product.id)
    assert refreshed.embedding is not None
    assert len(refreshed.embedding) == EMBEDDING_DIM
    assert refreshed.embedding_model == embedder.model_id


async def test_embed_is_idempotent(db_session, embedder) -> None:
    await _make_product(db_session)
    await embed_outdated(db_session, embedder)

    # Nothing is outdated on a second pass with the same provider.
    second = await embed_outdated(db_session, embedder)
    assert second == 0


async def test_embed_reembeds_on_model_change(db_session, embedder) -> None:
    # A row embedded by a different model is detected as outdated and re-embedded.
    product = await _make_product(
        db_session,
        embedding=[0.0] * EMBEDDING_DIM,
        embedding_model="stale:other-model",
    )

    count = await embed_outdated(db_session, embedder)

    assert count >= 1
    refreshed = await db_session.get(Product, product.id)
    assert refreshed.embedding_model == embedder.model_id


async def test_embedding_roundtrips_through_pgvector(db_session, embedder) -> None:
    product = await _make_product(db_session)
    await embed_outdated(db_session, embedder)

    # Read back via a fresh query to prove asyncpg/pgvector serialization works.
    stored = (await db_session.scalars(select(Product).where(Product.id == product.id))).one()
    assert len(stored.embedding) == EMBEDDING_DIM
    assert all(isinstance(x, float) for x in stored.embedding)
