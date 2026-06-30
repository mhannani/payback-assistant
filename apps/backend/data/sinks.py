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
        self._project = settings.vertex_project
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


def get_embedding_sink(session, settings: Settings | None = None) -> EmbeddingSink:
    """The sink for the configured retriever backend (pgvector → Postgres, bigquery → BigQuery)."""
    s = settings or get_settings()
    if s.retriever_backend == "bigquery":
        return BigQueryEmbeddingSink(s)
    return PostgresEmbeddingSink(session)
