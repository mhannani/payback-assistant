"""No-op filter — keep every candidate.

The baseline: no relevance cutoff, so the full nearest-N (noise tail included) flows
through. Useful as the control in an A/B comparison — it is the behaviour that exhibited
the candidate-pollution bug, so the other filters are measured against it.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.retrieval.filtering.base import CandidateFilter, ScoredCandidate


class NoFilter(CandidateFilter):
    def filter(self, candidates: Sequence[ScoredCandidate]) -> list[ScoredCandidate]:
        return list(candidates)
