"""Local, offline embedder (the default).

Runs a multilingual sentence-transformers model in-process, so the service needs no
credentials and works offline — and German queries match English product text (and
vice-versa) out of the box. The base class L2-normalizes the output.
"""

from __future__ import annotations

from functools import cached_property

from app.embeddings.base import Embedder


class LocalEmbedder(Embedder):
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    @cached_property
    def _model(self):
        # Imported lazily so the heavy dependency loads only when embeddings are
        # actually computed (not at module import), and the model loads once.
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self._model_name)

    @property
    def model_id(self) -> str:
        return f"local:{self._model_name}"

    @property
    def dimension(self) -> int:
        return self._model.get_embedding_dimension()

    def _embed_raw(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # show_progress_bar=False: keep stdout clean (no per-call progress bars) so command
        # output is just our own logs.
        vectors = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return vectors.tolist()
