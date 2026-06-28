"""Candidate filtering — pluggable relevance cutoffs for the vector arm.

``get_candidate_filter(strategy)`` returns the chosen strategy; everything else depends only
on the ``CandidateFilter`` contract. ``absolute`` is the default; ``autocut`` / ``relative``
are alternatives and ``none`` is the baseline.
"""

from __future__ import annotations

from app.retrieval.filtering.base import CandidateFilter, ScoredCandidate
from app.retrieval.filtering.factory import get_candidate_filter

__all__ = ["CandidateFilter", "ScoredCandidate", "get_candidate_filter"]
