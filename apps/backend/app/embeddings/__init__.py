"""Embeddings — provider-agnostic text-to-vector behind one interface.

``get_embedder()`` returns the configured implementation; everything else depends only
on the ``Embedder`` contract, so the provider is a config choice.
"""

from __future__ import annotations

from app.embeddings.base import Embedder
from app.embeddings.factory import get_embedder

__all__ = ["Embedder", "get_embedder"]
