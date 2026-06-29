"""Embedder contract tests — hermetic (no provider call): the base-class normalization, the
factory's provider selection, and the dimension guard. The concrete providers (OpenAI / Vertex)
are thin SDK adapters exercised against the real services in the deploy/seed path, not here."""

from __future__ import annotations

import math

import pytest

from app.config import Settings
from app.embeddings import Embedder, get_embedder
from app.embeddings.openai import OpenAIEmbedder


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


def test_factory_selects_provider() -> None:
    # OpenAI's client initializes without a network call; Vertex needs live GCP auth, so it's
    # exercised in the deploy/seed path rather than a hermetic unit test.
    assert isinstance(
        get_embedder(Settings(embedding_provider="openai", embedding_dim=1536)), OpenAIEmbedder
    )


def test_factory_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="unknown embedding_provider"):
        get_embedder(Settings(embedding_provider="nonsense"))


def test_factory_rejects_dimension_mismatch() -> None:
    # A provider whose vectors don't fit the declared dimension must fail at construction
    # (loudly), not later mid-embed or by writing mismatched vectors. OpenAI emits 1536-d, so
    # configuring a different EMBEDDING_DIM is the mismatch.
    with pytest.raises(ValueError, match="EMBEDDING_DIM"):
        get_embedder(Settings(embedding_provider="openai", embedding_dim=384))
