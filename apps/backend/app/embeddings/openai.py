"""OpenAI embedder.

One of the two managed providers behind the ``Embedder`` interface (the default). The SDK is
imported inside ``__init__`` so this module loads even before a client is constructed.
"""

from __future__ import annotations

from app.config import Settings
from app.embeddings.base import Embedder
from app.embeddings.dims import resolved_dimension


class OpenAIEmbedder(Embedder):
    def __init__(self, settings: Settings) -> None:
        self._model_name = settings.openai_model
        self._dimension = resolved_dimension(settings)
        # SDK imported here (not at module top) so this module loads without `openai`
        # installed; it only matters when an OpenAI embedder is actually constructed.
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key)

    @property
    def model_id(self) -> str:
        return f"openai:{self._model_name}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def _embed_raw(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._model_name, input=texts)
        # Sort by index — the API may return items out of order.
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]
