"""Select a ranking strategy by name.

One place maps a strategy name to a concrete ``Ranker``, so callers depend only on the
interface and the active strategy is a config choice. ``constrained`` is the default
(relevance-first with a hard guardrail); ``mmr`` and ``zscore`` are alternatives kept for
A/B comparison in the evaluation harness.
"""

from __future__ import annotations

from app.retrieval.ranking.base import Ranker
from app.retrieval.ranking.constrained import ConstrainedRanker
from app.retrieval.ranking.mmr import MmrRanker
from app.retrieval.ranking.zscore import ZScoreRanker

DEFAULT_STRATEGY = "constrained"


def get_ranker(strategy: str = DEFAULT_STRATEGY) -> Ranker:
    """Build the ranker named by ``strategy``."""
    match strategy:
        case "constrained":
            return ConstrainedRanker()
        case "mmr":
            return MmrRanker()
        case "zscore":
            return ZScoreRanker()
        case other:
            raise ValueError(
                f"unknown ranking strategy {other!r}; expected constrained, mmr, or zscore"
            )
