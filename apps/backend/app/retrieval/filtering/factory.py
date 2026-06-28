"""Select a candidate-filter strategy by name.

``absolute`` is the default (a tuned distance ceiling — most robust on this catalog);
``autocut`` and ``relative`` are alternatives, and ``none`` is the baseline for A/B
comparison.
"""

from __future__ import annotations

from app.retrieval.filtering.absolute import DEFAULT_CEILING, AbsoluteCeilingFilter
from app.retrieval.filtering.autocut import AutoCutFilter
from app.retrieval.filtering.base import CandidateFilter
from app.retrieval.filtering.none import NoFilter
from app.retrieval.filtering.relative import RelativeThresholdFilter

DEFAULT_STRATEGY = "absolute"


def get_candidate_filter(
    strategy: str = DEFAULT_STRATEGY, *, ceiling: float = DEFAULT_CEILING
) -> CandidateFilter:
    """Build the candidate filter named by ``strategy`` (``ceiling`` tunes 'absolute')."""
    match strategy:
        case "absolute":
            return AbsoluteCeilingFilter(ceiling=ceiling)
        case "autocut":
            return AutoCutFilter()
        case "relative":
            return RelativeThresholdFilter()
        case "none":
            return NoFilter()
        case other:
            raise ValueError(
                f"unknown filter strategy {other!r}; expected absolute, autocut, relative, or none"
            )
