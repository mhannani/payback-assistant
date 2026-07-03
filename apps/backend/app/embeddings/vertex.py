"""Vertex AI embedder.

The GCP-native provider behind the ``Embedder`` interface (OpenAI is the default). The SDK is
imported inside ``__init__`` so this module loads even before a client is constructed.

Auth: Vertex uses Google Application Default Credentials, not an API key — on Cloud Run the
attached service account authenticates automatically (no secret to store), so this embedder takes
a project + location rather than a key.
"""

from __future__ import annotations

from app.config import Settings
from app.embeddings.base import Embedder
from app.embeddings.dims import resolved_dimension


class VertexEmbedder(Embedder):
    def __init__(self, settings: Settings) -> None:
        self._model_name = settings.vertex_model
        self._dimension = resolved_dimension(settings)
        # The SDK is imported here (not at module top) so this module loads even when
        # google-cloud-aiplatform is not installed; importing it only matters when a
        # Vertex embedder is actually constructed, i.e. when Vertex is the chosen
        # provider. Init binds the project/region once for the lifetime of the embedder.
        import vertexai
        from vertexai.language_models import TextEmbeddingModel

        vertexai.init(project=settings.vertexai_project, location=settings.vertexai_location)
        self._model = TextEmbeddingModel.from_pretrained(self._model_name)

    @property
    def model_id(self) -> str:
        return f"vertex:{self._model_name}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def _embed_raw(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [embedding.values for embedding in self._model.get_embeddings(texts)]
