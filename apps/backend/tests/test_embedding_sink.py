"""Embedding-sink selection tests — hermetic (no DB, no BigQuery client built)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.config import Settings
from data.sinks import BigQueryEmbeddingSink, PostgresEmbeddingSink, get_embedding_sink


def test_pgvector_backend_selects_postgres_sink() -> None:
    sink = get_embedding_sink(MagicMock(), Settings(retriever_backend="pgvector"))
    assert isinstance(sink, PostgresEmbeddingSink)


def test_bigquery_backend_selects_bigquery_sink() -> None:
    # Constructed but the BQ client is lazy, so no GCP call happens here.
    sink = get_embedding_sink(
        MagicMock(), Settings(retriever_backend="bigquery", vertexai_project="proj")
    )
    assert isinstance(sink, BigQueryEmbeddingSink)
