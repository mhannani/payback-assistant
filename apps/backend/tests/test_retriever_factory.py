"""Tests for the retriever factory — config selects the stack (no DB needed)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.retrieval.factory import get_retriever
from app.retrieval.filtering.autocut import AutoCutFilter
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.ranking.mmr import MmrRanker
from app.retrieval.vector_index import BigQueryVectorIndex, PgVectorIndex


class _FakeEmbedder:
    model_id = "openai:text-embedding-3-small"
    dimension = 1536

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * self.dimension


def test_factory_builds_hybrid_with_pgvector_index() -> None:
    settings = Settings(filter_strategy="autocut", ranking_strategy="mmr")
    retriever = get_retriever(embedder=_FakeEmbedder(), settings=settings)
    assert isinstance(retriever, HybridRetriever)
    assert isinstance(retriever._vector_index, PgVectorIndex)
    # The configured strategies were wired in (not the defaults).
    assert isinstance(retriever._ranker, MmrRanker)
    assert isinstance(retriever._filter, AutoCutFilter)


def test_factory_builds_hybrid_with_bigquery_index() -> None:
    settings = Settings(retriever_backend="bigquery", vertexai_project="proj")
    retriever = get_retriever(embedder=_FakeEmbedder(), settings=settings)
    assert isinstance(retriever, HybridRetriever)
    assert isinstance(retriever._vector_index, BigQueryVectorIndex)  # GCP: BQ semantic + PG lexical


def test_factory_bigquery_requires_project() -> None:
    with pytest.raises(ValueError, match="VERTEXAI_PROJECT"):
        get_retriever(
            embedder=_FakeEmbedder(),
            settings=Settings(retriever_backend="bigquery", vertexai_project=None),
        )


def test_factory_threads_retrieval_tuning() -> None:
    # filter_ceiling reaches the absolute filter; fulltext_min_rank reaches the retriever.
    settings = Settings(filter_ceiling=0.42, fulltext_min_rank=0.05)
    retriever = get_retriever(embedder=_FakeEmbedder(), settings=settings)
    assert retriever._filter._ceiling == 0.42
    assert retriever._fulltext_min_rank == 0.05


def test_factory_rejects_unknown_backend() -> None:
    settings = Settings(retriever_backend="nope")
    with pytest.raises(ValueError, match="unknown retriever_backend"):
        get_retriever(embedder=_FakeEmbedder(), settings=settings)
