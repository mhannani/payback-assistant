"""Relative distance threshold — kept as an instructive (inferior) alternative.

Keep candidates within a tolerance band of the *best* match. Intuitive, and what many
first reach for, but it is included here mainly to document *why* it is not the default:
on this catalog it fails at both ends of the quality range.

Algorithm
---------
    keep = { c : c.distance ≤ d_best · (1 + δ) }

with ``d_best`` the smallest distance and ``δ`` a tolerance (default 0.5 → 50 %).

Why it is NOT the default (measured):
  - Best match excellent (shampoo, d_best ≈ 0.19 → band ≤ 0.29): cuts genuine shampoos at
    0.31–0.47 → false negatives.
  - Best match itself poor (a no-real-match query, d_best ≈ 0.59 → band ≤ 0.88): keeps the
    noise, because a band around a bad anchor is still bad → false positives.
The flaw is that it has no notion of *absolute* quality — it scales off an anchor that may
itself be good or bad. The absolute-ceiling filter avoids this; see ``absolute.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.retrieval.filtering.base import CandidateFilter, ScoredCandidate

DEFAULT_TOLERANCE = 0.5


class RelativeThresholdFilter(CandidateFilter):
    def __init__(self, tolerance: float = DEFAULT_TOLERANCE) -> None:
        self._tolerance = tolerance

    def filter(self, candidates: Sequence[ScoredCandidate]) -> list[ScoredCandidate]:
        if not candidates:
            return []
        best = min(c.distance for c in candidates)
        ceiling = best * (1 + self._tolerance)
        return [c for c in candidates if c.distance <= ceiling]
