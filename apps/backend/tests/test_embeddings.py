"""Embedder tests — the local model is baked into the image, so these run offline."""

from __future__ import annotations

import math

import pytest

from app.config import Settings
from app.db.models import EMBEDDING_DIM
from app.embeddings import Embedder, get_embedder
from app.embeddings.local import LocalEmbedder


class _RawEmbedder(Embedder):
    """A fake provider that returns deliberately non-unit vectors."""

    model_id = "fake:raw"
    dimension = 3

    def _embed_raw(self, texts: list[str]) -> list[list[float]]:
        return [[3.0, 4.0, 0.0] for _ in texts]  # norm 5, clearly not unit length


def test_local_dimension_matches_schema(embedder) -> None:
    assert embedder.dimension == EMBEDDING_DIM


def test_embed_texts_shape(embedder) -> None:
    vectors = embedder.embed_texts(["Bio Spaghetti", "günstige Windeln"])
    assert len(vectors) == 2
    assert all(len(v) == EMBEDDING_DIM for v in vectors)


def test_embed_texts_empty_returns_empty(embedder) -> None:
    assert embedder.embed_texts([]) == []


def test_embedding_is_deterministic(embedder) -> None:
    first = embedder.embed_query("Vollkorn Pasta")
    second = embedder.embed_query("Vollkorn Pasta")
    assert first == pytest.approx(second)


def test_embedding_is_l2_normalized(embedder) -> None:
    # Cosine HNSW index expects unit vectors.
    vector = embedder.embed_query("Olivenöl")
    assert math.sqrt(sum(x * x for x in vector)) == pytest.approx(1.0, abs=1e-3)


def test_contract_normalizes_any_provider_output() -> None:
    # The base class normalizes whatever a provider returns, so every impl (current or
    # future) yields unit vectors for the cosine index — no impl can forget.
    [vector] = _RawEmbedder().embed_texts(["x"])
    assert vector == pytest.approx([0.6, 0.8, 0.0])  # [3,4,0] / 5
    assert math.sqrt(sum(x * x for x in vector)) == pytest.approx(1.0)


def test_model_id_identifies_provider_and_model(embedder) -> None:
    assert embedder.model_id == "local:paraphrase-multilingual-MiniLM-L12-v2"


def test_factory_selects_local_by_default() -> None:
    assert isinstance(get_embedder(Settings(embedding_provider="local")), LocalEmbedder)


def test_factory_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="unknown embedding_provider"):
        get_embedder(Settings(embedding_provider="nonsense"))


def test_factory_rejects_dimension_mismatch(monkeypatch) -> None:
    # A provider whose vectors don't fit the fixed-size schema column must fail at
    # construction (loudly), not later mid-embed or by writing mismatched vectors.
    class _WrongDim(_RawEmbedder):
        dimension = EMBEDDING_DIM + 1

    monkeypatch.setattr("app.embeddings.factory.LocalEmbedder", lambda _name: _WrongDim())
    with pytest.raises(ValueError, match="products.embedding column"):
        get_embedder(Settings(embedding_provider="local"))
