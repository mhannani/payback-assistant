"""Create the BigQuery vector table and its vector index (the BigQuery analogue of data.init_db).

Runs only on the GCP / ``RETRIEVER_BACKEND=bigquery`` path, after ``init_db`` + ``seed`` populate
the Postgres catalog. It creates the ``products`` table that holds the vectors BigQuery searches
(product_id, partner, tags, embedding, embedding_model) and a ``CREATE VECTOR INDEX`` (IVF, cosine)
— the BigQuery counterpart of the pgvector HNSW index in ``db/init.sql``. Idempotent: ``IF NOT
EXISTS`` throughout, so it is safe to re-run before every embed.

The embedding column width is the deployment's dimension (``settings.embedding_dim``, derived from
the provider+model) — the same single source ``init_db`` uses, so the two stores never disagree.
"""

from __future__ import annotations

from app.config import get_settings


def init_bq() -> None:
    """Create the dataset table + vector index for the configured BigQuery target."""
    from google.cloud import bigquery

    s = get_settings()
    client = bigquery.Client(project=s.vertex_project)
    dataset = f"{s.vertex_project}.{s.bigquery_dataset}"
    table = f"{dataset}.{s.bigquery_table}"
    dim = s.embedding_dim

    client.create_dataset(bigquery.Dataset(dataset), exists_ok=True)
    client.query(
        f"""
        CREATE TABLE IF NOT EXISTS `{table}` (
          product_id      STRING NOT NULL,
          partner         STRING,
          tags            ARRAY<STRING>,
          embedding       ARRAY<FLOAT64>,  -- {dim}-d; validated by the embedder/dimension guard
          embedding_model STRING
        )
        """
    ).result()
    # IVF + cosine — the warehouse-scale ANN index VECTOR_SEARCH uses (counterpart of HNSW on pgvector).
    client.query(
        f"""
        CREATE VECTOR INDEX IF NOT EXISTS payback_products_idx
        ON `{table}`(embedding)
        OPTIONS (index_type = 'IVF', distance_type = 'COSINE')
        """
    ).result()
    print(f"Initialized BigQuery vector table {table} ({dim}-d) + index.")


if __name__ == "__main__":
    init_bq()
