"""Compute and store product embeddings.

A separate step from seeding: ``make seed`` loads the catalog (vectors empty), then
``make embed`` fills them. It is provenance-aware — each row records which model
produced its vector (``embedding_model``), so a row is (re)embedded when it has no
vector OR was embedded by a different model. Switching ``embedding_provider`` and
re-running therefore re-embeds the catalog automatically; re-running with the same
provider is a no-op. Vectors from different models aren't comparable, so this keeps
the whole catalog on one model.

Each product holds ONE live embedding: switching providers overwrites it (and
switching back re-embeds again). That is deliberate — search only ever compares
against the current provider's vectors, so storing every model's vectors would be
unused data. The scale-up, if instant switch-back or serving two embedders at once
were ever needed, is a ``product_embeddings(product_id, model_id, embedding)`` table.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import or_, select

from app.db.models import Product
from app.db.session import SessionFactory, engine
from app.embeddings import Embedder, get_embedder


def _embedding_input(product: Product) -> str:
    """Text fed to the embedder — the same name + description the full-text index uses."""
    return f"{product.name}. {product.description or ''}".strip()


async def embed_outdated(session, embedder: Embedder, *, batch_size: int = 64) -> int:
    """Embed products with no vector or one from a different model. Returns the count.

    Flushes the updates but does not commit — the caller owns the transaction boundary.
    """
    stmt = select(Product).where(
        or_(
            Product.embedding.is_(None),
            Product.embedding_model.is_distinct_from(embedder.model_id),
        )
    )
    products = list((await session.scalars(stmt)).all())
    if not products:
        return 0

    for start in range(0, len(products), batch_size):
        batch = products[start : start + batch_size]
        vectors = embedder.embed_texts([_embedding_input(p) for p in batch])
        for product, vector in zip(batch, vectors, strict=True):
            # Defense-in-depth: the factory already guarantees the embedder fits the
            # schema, but this catches a provider that returns an off-size vector.
            if len(vector) != embedder.dimension:
                raise ValueError(
                    f"embedder returned dim {len(vector)}, expected {embedder.dimension}"
                )
            product.embedding = vector
            product.embedding_model = embedder.model_id
        await session.flush()

    return len(products)


async def _main() -> None:
    embedder = get_embedder()
    async with SessionFactory() as session:
        count = await embed_outdated(session, embedder)
        await session.commit()
    print(f"Embedded {count} products with {embedder.model_id}.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
