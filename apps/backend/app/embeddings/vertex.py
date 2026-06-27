"""Vertex AI embedder.

A real implementation behind the same interface as the local embedder, so production
can serve embeddings from Vertex by config alone. It is not exercised in the default
setup (which needs no cloud credentials); the SDK is imported inside ``__init__`` so
this module loads even when ``google-cloud-aiplatform`` is not installed.

Auth: Vertex uses Google Application Default Credentials, not an API key — on Cloud Run
the attached service account authenticates automatically (no secret to store), so this
embedder takes a project + location rather than a key.
"""

from __future__ import annotations

from app.config import Settings
from app.embeddings.base import Embedder

# Output dimension per Vertex embedding model — the factory checks this against the
# physical schema dimension, so a provider/schema mismatch fails loudly at startup.
_MODEL_DIMS = {"text-multilingual-embedding-002": 768, "text-embedding-005": 768}


class VertexEmbedder(Embedder):
    def __init__(self, settings: Settings) -> None:
        self._model_name = settings.vertex_model
        self._dimension = _MODEL_DIMS.get(self._model_name, 768)
        # The SDK is imported here (not at module top) so this module loads even when
        # google-cloud-aiplatform is not installed; importing it only matters when a
        # Vertex embedder is actually constructed, i.e. when Vertex is the chosen
        # provider. Init binds the project/region once for the lifetime of the embedder.
        import vertexai
        from vertexai.language_models import TextEmbeddingModel

        vertexai.init(project=settings.vertex_project, location=settings.vertex_location)
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
