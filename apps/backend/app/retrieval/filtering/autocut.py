"""AutoCut — cut the candidate list at the largest distance "gap".

Parameter-free alternative to a fixed ceiling: relevant results cluster at low distances,
then there is a jump (a "cliff") to the noise floor. AutoCut finds the biggest jump between
consecutive sorted distances and keeps everything before it. This is Weaviate's ``autocut``.

Algorithm
---------
With candidates sorted by ascending distance ``d_0 ≤ d_1 ≤ … ≤ d_n``, the gaps are

    Δ_i = d_{i+1} − d_i

Cut after the index ``i*`` with the largest gap (within a search window), keeping
``d_0 … d_{i*}``. For "günstige Windeln" the gap 0.49 → 0.61 is the largest, so the four
diapers are kept and the noise dropped.

Trade-off: it adapts per query and needs no tuned constant, but it is fragile when the
distance distribution is smooth (no clear gap) — e.g. a query with no real match has a
uniformly mediocre tail and no cliff, so AutoCut may keep noise. The absolute-ceiling
filter handles that case better; this strategy is kept for comparison.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.retrieval.filtering.base import CandidateFilter, ScoredCandidate

# Only look for the cliff within the most-relevant prefix; a gap deep in the noise tail is
# not a meaningful signal/noise boundary.
DEFAULT_WINDOW = 10


class AutoCutFilter(CandidateFilter):
    def __init__(self, window: int = DEFAULT_WINDOW) -> None:
        self._window = window

    def filter(self, candidates: Sequence[ScoredCandidate]) -> list[ScoredCandidate]:
        ordered = sorted(candidates, key=lambda c: c.distance)
        if len(ordered) <= 1:
            return list(ordered)

        window = min(self._window, len(ordered) - 1)
        cut_after = max(range(window), key=lambda i: ordered[i + 1].distance - ordered[i].distance)
        return ordered[: cut_after + 1]
