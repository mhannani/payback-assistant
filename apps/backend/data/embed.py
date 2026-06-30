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

from app.config import get_settings
from app.db.models import Product
from app.db.session import SessionFactory, engine
from app.embeddings import Embedder, get_embedder
from data.sinks import EmbeddedProduct, EmbeddingSink, get_embedding_sink


def _embedding_input(product: Product) -> str:
    """Text fed to the embedder — the same name + description the full-text index uses."""
    return f"{product.name}. {product.description or ''}".strip()


async def _products_to_embed(session, embedder: Embedder, *, all_rows: bool) -> list[Product]:
    """The catalog rows to embed — always read from Postgres (the source of truth).

    For Postgres (pgvector) we embed only outdated rows (no vector, or a different model) using the
    stored provenance. For BigQuery there is no per-row provenance in Postgres, so we (re)embed all
    rows and let the sink's MERGE keep one live vector per product.
    """
    stmt = select(Product)
    if not all_rows:
        stmt = stmt.where(
            or_(
                Product.embedding.is_(None),
                Product.embedding_model.is_distinct_from(embedder.model_id),
            )
        )
    return list((await session.scalars(stmt)).all())


async def embed_into(
    session, embedder: Embedder, sink: EmbeddingSink, *, batch_size: int = 64, all_rows: bool = False
) -> int:
    """Embed the catalog and write the vectors to ``sink``. Returns the count embedded."""
    products = await _products_to_embed(session, embedder, all_rows=all_rows)
    if not products:
        return 0

    for start in range(0, len(products), batch_size):
        batch = products[start : start + batch_size]
        vectors = embedder.embed_texts([_embedding_input(p) for p in batch])
        rows = []
        for product, vector in zip(batch, vectors, strict=True):
            # Defense-in-depth: the factory already guarantees the embedder fits the schema, but
            # this catches a provider that returns an off-size vector.
            if len(vector) != embedder.dimension:
                raise ValueError(
                    f"embedder returned dim {len(vector)}, expected {embedder.dimension}"
                )
            rows.append(EmbeddedProduct(product=product, vector=vector, model_id=embedder.model_id))
        await sink.write(rows)

    return len(products)


async def _main() -> None:
    embedder = get_embedder()
    backend = get_settings().retriever_backend
    async with SessionFactory() as session:
        sink = get_embedding_sink(session)
        # BigQuery has no per-row provenance in Postgres, so embed all rows (MERGE keeps one live).
        count = await embed_into(session, embedder, sink, all_rows=backend == "bigquery")
        await session.commit()
    print(f"Embedded {count} products with {embedder.model_id} (backend: {backend}).")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
