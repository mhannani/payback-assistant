"""Ranking — pluggable strategies for the final ordering of fused candidates.

``get_ranker(strategy)`` returns the chosen strategy; everything else depends only on the
``Ranker`` contract. ``constrained`` is the default; ``mmr`` and ``zscore`` are alternatives
for A/B comparison.
"""

from __future__ import annotations

from app.retrieval.ranking.base import Ranker
from app.retrieval.ranking.factory import get_ranker

__all__ = ["Ranker", "get_ranker"]
