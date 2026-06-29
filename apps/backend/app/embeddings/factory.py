"""Select the configured embedder.

One place maps the ``embedding_provider`` setting to a concrete embedder, so the rest
of the app depends only on the ``Embedder`` interface.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.embeddings.base import Embedder
from app.embeddings.openai import OpenAIEmbedder
from app.embeddings.vertex import VertexEmbedder


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Build the embedder named by ``embedding_provider`` (a managed cloud provider).

    Fails loudly at construction if the provider's vector dimension doesn't match the schema's
    declared ``embedding_dim`` — the alternative (failing later, mid-embed, or silently writing
    mismatched vectors into the fixed-size column) is a worse, harder-to-trace failure.
    """
    s = settings or get_settings()
    match s.embedding_provider:
        case "vertex":
            embedder: Embedder = VertexEmbedder(s)
        case "openai":
            embedder = OpenAIEmbedder(s)
        case other:
            raise ValueError(f"unknown embedding_provider {other!r}; expected vertex or openai")

    if embedder.dimension != s.embedding_dim:
        raise ValueError(
            f"provider {s.embedding_provider!r} emits {embedder.dimension}-d vectors but "
            f"EMBEDDING_DIM is set to {s.embedding_dim}. Set EMBEDDING_DIM to {embedder.dimension} "
            f"(it sizes the products.embedding column, applied by data.init_db) and re-provision."
        )
    return embedder
