"""Resolve the embedding dimension for the configured provider + model.

The dimension is a property of the chosen model, not a separately-configured value — so it is
*derived* here rather than set by hand (where it could drift and only fail at the dimension guard).
We read it from LiteLLM's model metadata (``output_vector_size``) rather than maintaining our own
model→dim table: LiteLLM already ships and updates that data, and it's an offline local lookup, so
this stays import-safe (it can size the schema column before any embedding client exists).
"""

from __future__ import annotations

from app.config import Settings

# pgvector's HNSW index cannot index vectors wider than this. A model above it would pass the
# dimension lookup and then fail deep in schema creation, so we reject it up front. (Our own
# constraint, not a model property — hence not from LiteLLM.)
HNSW_MAX_DIM = 2000


def resolved_dimension(settings: Settings) -> int:
    """The embedding dimension implied by the configured provider + model.

    Raises ``ValueError`` for an unknown model (no fabricated default) or one wider than the HNSW
    index can handle, so a misconfiguration fails with a clear message here rather than an opaque
    error during schema creation.
    """
    # Imported lazily so the module loads without litellm installed; the lookup is offline.
    import litellm

    provider = settings.embedding_provider
    model = settings.openai_model if provider == "openai" else settings.vertex_model

    try:
        dim = litellm.get_model_info(model)["output_vector_size"]
    except Exception:
        raise ValueError(
            f"no known embedding dimension for provider {provider!r} model {model!r}; "
            f"use a model LiteLLM knows the output_vector_size for."
        ) from None

    if dim is None:
        raise ValueError(f"{provider}/{model} is not a known embedding model (no output dimension).")
    if dim > HNSW_MAX_DIM:
        raise ValueError(
            f"{provider}/{model} emits {dim}-d vectors; the pgvector HNSW index caps at "
            f"{HNSW_MAX_DIM}-d. Choose a model at or under {HNSW_MAX_DIM}-d."
        )
    return dim
