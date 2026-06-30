"""Embedder contract tests — hermetic (no provider call): the base-class normalization, the
factory's provider selection, and the dimension guard. The concrete providers (OpenAI / Vertex)
are thin SDK adapters exercised against the real services in the deploy/seed path, not here."""

from __future__ import annotations

import math

import pytest

from app.config import Settings
from app.embeddings import Embedder
from app.embeddings.dims import resolved_dimension


class _RawEmbedder(Embedder):
    """A fake provider that returns deliberately non-unit vectors."""

    model_id = "fake:raw"
    dimension = 3

    def _embed_raw(self, texts: list[str]) -> list[list[float]]:
        return [[3.0, 4.0, 0.0] for _ in texts]  # norm 5, clearly not unit length


def test_contract_normalizes_any_provider_output() -> None:
    # The base class normalizes whatever a provider returns, so every impl (current or
    # future) yields unit vectors for the cosine index — no impl can forget.
    [vector] = _RawEmbedder().embed_texts(["x"])
    assert vector == pytest.approx([0.6, 0.8, 0.0])  # [3,4,0] / 5
    assert math.sqrt(sum(x * x for x in vector)) == pytest.approx(1.0)


def test_embed_texts_empty_returns_empty() -> None:
    assert _RawEmbedder().embed_texts([]) == []


def test_dimension_derived_per_provider() -> None:
    # The dimension follows from the configured provider + model — no hand-set value.
    assert resolved_dimension(Settings(embedding_provider="openai")) == 1536
    assert resolved_dimension(Settings(embedding_provider="vertex")) == 768


def test_dimension_rejects_unknown_model() -> None:
    # A typo'd model must fail loudly, not silently size the schema with a fabricated default.
    with pytest.raises(ValueError, match="no known embedding dimension"):
        resolved_dimension(Settings(embedding_provider="openai", openai_model="text-embedding-9-xl"))


def test_dimension_rejects_model_too_wide_for_hnsw() -> None:
    # text-embedding-3-large is 3072-d; the pgvector HNSW index caps at 2000-d, so it's rejected
    # up front with a clear message rather than failing deep in schema creation.
    with pytest.raises(ValueError, match="HNSW index caps"):
        resolved_dimension(Settings(embedding_provider="openai", openai_model="text-embedding-3-large"))
