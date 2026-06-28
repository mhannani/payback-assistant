"""The candidate-filter contract.

A vector ANN search always returns the *nearest* N products, even when most of them are
not actually relevant — so for "günstige Windeln" the four real diapers are followed by a
tail of unrelated-but-least-far items (shower gel, coffee). A ``CandidateFilter`` removes
that noise tail before the candidates go into fusion and ranking.

It filters on the **raw cosine distance** (0 = identical, 2 = opposite): the raw distance
keeps a clear signal (real matches cluster low, noise sits on a higher floor), whereas the
post-fusion RRF score is compressed and can't separate them. Strategies are interchangeable
behind this interface so the cutoff method is a config / A/B choice, mirroring the rankers.

Scope: this gates the **vector arm only**. The keyword arm has no comparable distance scale
(``ts_rank`` is unbounded and query-dependent), so it is gated differently — by the ``@@``
match requirement plus a ``ts_rank`` floor (``settings.fulltext_min_rank``) applied in
``fulltext_candidates`` — rather than by a ``CandidateFilter``. Both arms therefore feed
fusion a relevance-disciplined list; they just use the gate appropriate to their score scale.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """A vector hit with its raw cosine distance (smaller = closer/more relevant)."""

    product_id: uuid.UUID
    distance: float


class CandidateFilter(ABC):
    @abstractmethod
    def filter(self, candidates: Sequence[ScoredCandidate]) -> list[ScoredCandidate]:
        """Return the subset judged relevant, preserving the input (distance) order."""
