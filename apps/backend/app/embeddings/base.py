"""The embedder contract.

An ``Embedder`` turns text into vectors for semantic search. Concrete impls (local,
Vertex, OpenAI) are interchangeable behind this interface, so the catalog and the
query are always embedded the same way and the provider is a config choice — no
vendor lock-in. ``model_id`` identifies the producing model so the catalog can be
re-embedded when the provider changes and stale vectors are never compared.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod


class Embedder(ABC):
    """Turns text into fixed-size vectors for semantic search.

    Concrete impls only implement ``_embed_raw``; the base then L2-normalizes the
    result. Normalization lives here (not per impl) because the catalog's HNSW index
    uses cosine distance, which assumes unit vectors — owning it in the contract means
    no provider (OpenAI, Vertex, or a future one) can forget and silently
    degrade search quality.
    """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Stable identifier of the producing model, e.g. 'openai:text-embedding-3-small'."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Length of the vectors this embedder produces."""

    @abstractmethod
    def _embed_raw(self, texts: list[str]) -> list[list[float]]:
        """Provider-specific embedding; one vector per input, same order. Not normalized."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts as L2-normalized (unit) vectors for cosine search."""
        return [_l2_normalize(vector) for vector in self._embed_raw(texts)]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string. Same space as ``embed_texts`` by default."""
        return self.embed_texts([text])[0]


def _l2_normalize(vector: list[float]) -> list[float]:
    """Scale a vector to unit length; a zero vector is returned unchanged."""
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        return vector
    return [component / norm for component in vector]
