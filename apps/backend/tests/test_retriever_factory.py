"""Tests for the retriever factory — config selects the stack (no DB needed)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.retrieval.factory import get_retriever
from app.retrieval.filtering.autocut import AutoCutFilter
from app.retrieval.pgvector import PgVectorRetriever
from app.retrieval.ranking.mmr import MmrRanker


def test_factory_builds_pgvector_with_configured_strategies(embedder) -> None:
    settings = Settings(filter_strategy="autocut", ranking_strategy="mmr")
    retriever = get_retriever(embedder=embedder, settings=settings)
    assert isinstance(retriever, PgVectorRetriever)
    # The configured strategies were wired in (not the defaults).
    assert isinstance(retriever._ranker, MmrRanker)
    assert isinstance(retriever._filter, AutoCutFilter)


def test_factory_threads_retrieval_tuning(embedder) -> None:
    # filter_ceiling reaches the absolute filter; fulltext_min_rank reaches the retriever.
    settings = Settings(filter_ceiling=0.42, fulltext_min_rank=0.05)
    retriever = get_retriever(embedder=embedder, settings=settings)
    assert retriever._filter._ceiling == 0.42
    assert retriever._fulltext_min_rank == 0.05


def test_factory_rejects_unknown_backend(embedder) -> None:
    settings = Settings(retriever_backend="nope")
    with pytest.raises(ValueError, match="unknown retriever_backend"):
        get_retriever(embedder=embedder, settings=settings)
