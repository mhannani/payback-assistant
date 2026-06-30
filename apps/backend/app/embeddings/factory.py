"""Select the configured embedder.

One place maps the ``embedding_provider`` setting to a concrete embedder, so the rest
of the app depends only on the ``Embedder`` interface.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.embeddings.base import Embedder
from app.embeddings.dims import resolved_dimension
from app.embeddings.openai import OpenAIEmbedder
from app.embeddings.vertex import VertexEmbedder


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Build the embedder named by ``embedding_provider`` (a managed cloud provider).

    The provider/model dimension is validated FIRST (unknown model or one too wide for the index
    is rejected here, before any cloud SDK is constructed). The post-construction equality check is
    a cheap consistency guard — the embedder's dimension and the schema's both derive from the same
    table, so a mismatch would signal a table bug, not a config error.
    """
    s = settings or get_settings()
    expected_dim = resolved_dimension(s)  # raises on unknown / too-wide model, pre-construction

    match s.embedding_provider:
        case "vertex":
            embedder: Embedder = VertexEmbedder(s)
        case "openai":
            embedder = OpenAIEmbedder(s)
        case other:
            raise ValueError(f"unknown embedding_provider {other!r}; expected vertex or openai")

    if embedder.dimension != expected_dim:
        raise ValueError(
            f"internal dimension table inconsistency: {s.embedding_provider} embedder reports "
            f"{embedder.dimension}-d but the schema expects {expected_dim}-d."
        )
    return embedder
