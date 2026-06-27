"""Select the configured embedder.

One place maps the ``embedding_provider`` setting to a concrete embedder, so the rest
of the app depends only on the ``Embedder`` interface.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.db.models import EMBEDDING_DIM
from app.embeddings.base import Embedder
from app.embeddings.local import LocalEmbedder
from app.embeddings.openai import OpenAIEmbedder
from app.embeddings.vertex import VertexEmbedder


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Build the embedder named by ``embedding_provider``.

    Fails loudly at construction if the provider's vectors don't fit the schema's
    fixed-size ``embedding`` column — the alternative (failing later, mid-embed, or
    silently writing mismatched vectors) is a worse, harder-to-trace failure.
    """
    s = settings or get_settings()
    match s.embedding_provider:
        case "local":
            embedder: Embedder = LocalEmbedder(s.embedding_model_name)
        case "vertex":
            embedder = VertexEmbedder(s)
        case "openai":
            embedder = OpenAIEmbedder(s)
        case other:
            raise ValueError(
                f"unknown embedding_provider {other!r}; expected local, vertex, or openai"
            )

    if embedder.dimension != EMBEDDING_DIM:
        raise ValueError(
            f"provider {s.embedding_provider!r} emits {embedder.dimension}-d vectors but the "
            f"products.embedding column is {EMBEDDING_DIM}-d. Re-create the schema with a matching "
            f"vector dimension (EMBEDDING_DIM in app/db/models.py and db/init.sql) before using it."
        )
    return embedder
