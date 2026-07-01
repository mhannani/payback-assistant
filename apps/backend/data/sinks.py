"""Where computed embeddings are written — selected by the retriever backend.

The catalog rows always live in Postgres (the source of truth), but the vectors go to whichever
store the active retriever searches: the pgvector backend keeps them on the ``products`` row in
Postgres; the BigQuery backend loads them into the BigQuery vector table. An ``EmbeddingSink``
abstracts that write so the embed pipeline (``data/embed.py``) is backend-aware through one seam
rather than scattered branches.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.db.models import Product


@dataclass(frozen=True, slots=True)
class EmbeddedProduct:
    """One product's freshly computed vector plus the row fields the BigQuery table mirrors."""

    product: Product
    vector: list[float]
    model_id: str


class EmbeddingSink(ABC):
    """Writes computed embeddings to the store the active retriever reads from."""

    @abstractmethod
    async def write(self, rows: Sequence[EmbeddedProduct]) -> None:
        """Persist a batch of embeddings."""


class PostgresEmbeddingSink(EmbeddingSink):
    """Writes the vector onto the ``products`` row (pgvector). The session owns the transaction."""

    def __init__(self, session) -> None:
        self._session = session

    async def write(self, rows: Sequence[EmbeddedProduct]) -> None:
        for row in rows:
            row.product.embedding = row.vector
            row.product.embedding_model = row.model_id
        await self._session.flush()


class BigQueryEmbeddingSink(EmbeddingSink):
    """Loads embeddings (with the row fields BigQuery searches/returns) into the BQ vector table.

    Idempotent on ``product_id`` via MERGE, so re-running after a provider switch overwrites the
    vector rather than duplicating the row — mirroring the Postgres sink's one-live-vector model.
    """

    def __init__(self, settings: Settings) -> None:
        self._dataset = settings.bigquery_dataset
        self._table = settings.bigquery_table
        self._project = settings.vertexai_project
        self._client = None

    def _bq(self):
        if self._client is None:
            from google.cloud import bigquery

            self._client = bigquery.Client(project=self._project)
        return self._client

    async def write(self, rows: Sequence[EmbeddedProduct]) -> None:
        if not rows:
            return
        from google.cloud import bigquery

        client = self._bq()
        target = f"{self._project}.{self._dataset}.{self._table}"
        # Stage the batch, then MERGE into the target so an existing product_id is updated in place.
        staging = f"{target}_staging"
        records = [
            {
                "product_id": str(r.product.id),
                "partner": r.product.partner.slug,
                "tags": list(r.product.tags),
                "embedding": r.vector,
                "embedding_model": r.model_id,
            }
            for r in rows
        ]
        load = client.load_table_from_json(
            records,
            staging,
            job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
        )
        load.result()
        client.query(
            f"""
            MERGE `{target}` T USING `{staging}` S ON T.product_id = S.product_id
            WHEN MATCHED THEN UPDATE SET
              T.partner = S.partner, T.tags = S.tags,
              T.embedding = S.embedding, T.embedding_model = S.embedding_model
            WHEN NOT MATCHED THEN INSERT (product_id, partner, tags, embedding, embedding_model)
              VALUES (S.product_id, S.partner, S.tags, S.embedding, S.embedding_model)
            """
        ).result()
        self._ensure_vector_index(client, target)

    # BigQuery refuses an IVF vector index below this many rows ("Total rows N is smaller than min
    # allowed 5000 … Please use VECTOR_SEARCH … directly"). Below it, VECTOR_SEARCH does an exact
    # brute-force scan with no index — which is correct (and fast) at demo scale. The index is a
    # scale-path optimization (ADR 0003), so we build it only once the catalog is large enough.
    _BQ_VECTOR_INDEX_MIN_ROWS = 5000

    def _ensure_vector_index(self, client, target: str) -> None:
        """Build the ANN vector index — AFTER vectors are written, and only above BigQuery's minimum.

        Two BigQuery constraints shape this: (1) the index reads the column's arrays to derive the
        vector dimension, so it can't be built on an all-NULL column — hence it lives here, after the
        MERGE, not in init_bq on an empty table; (2) an IVF index requires ≥ 5000 rows, so on a small
        catalog we skip it and let VECTOR_SEARCH run brute-force (the retriever never references the
        index by name, so nothing else changes). IVF + cosine is the warehouse ANN index at scale —
        the BigQuery counterpart of pgvector's HNSW. ``IF NOT EXISTS`` keeps the re-run idempotent.
        """
        rows = next(iter(client.query(f"SELECT COUNT(*) AS n FROM `{target}`").result())).n
        if rows < self._BQ_VECTOR_INDEX_MIN_ROWS:
            print(
                f"BigQuery vector index skipped: {rows} rows < {self._BQ_VECTOR_INDEX_MIN_ROWS} "
                "(IVF minimum). VECTOR_SEARCH runs brute-force at this scale — no index needed."
            )
            return
        client.query(
            f"""
            CREATE VECTOR INDEX IF NOT EXISTS payback_products_idx
            ON `{target}`(embedding)
            OPTIONS (index_type = 'IVF', distance_type = 'COSINE')
            """
        ).result()


def get_embedding_sink(session, settings: Settings | None = None) -> EmbeddingSink:
    """The sink for the configured retriever backend (pgvector → Postgres, bigquery → BigQuery)."""
    s = settings or get_settings()
    if s.retriever_backend == "bigquery":
        return BigQueryEmbeddingSink(s)
    return PostgresEmbeddingSink(session)
