"""Maximal Marginal Relevance (MMR) — a diversity-aware alternative strategy.

Carbonell & Goldstein, 1998. MMR builds the result list greedily, each step trading off
relevance against *redundancy* with what is already chosen — so it avoids stacking many
near-identical results (here: many items from the same partner).

Algorithm
---------
Let ``R`` be the candidate set, ``S`` the items already selected, ``rel(d)`` the
candidate's relevance (its fused score, min-max scaled to [0, 1] so it is comparable to the
redundancy term), and ``red(d, S)`` the redundancy of ``d`` against what is already chosen.
Pick repeatedly:

    MMR = argmax_{ d ∈ R \\ S } [ λ · rel(d) − (1 − λ) · red(d, S) ]

with ``λ ∈ [0, 1]`` the relevance/diversity trade-off (λ→1 pure relevance, λ→0 pure
diversity, λ≈0.7 here so relevance leads).

Redundancy = **graded** partner over-representation. The canonical MMR uses
``max_{d'∈S} sim(d, d')``; with a 0/1 same-partner indicator that ``max`` collapses to "has
this partner appeared at all", giving every 2nd/3rd/4th item from a partner the *same*
penalty — no escalation. Instead we count how many of the already-selected items share the
candidate's partner and normalise to [0, 1] by the running selection size:

    red(d, S) = |{ d' ∈ S : partner(d') == partner(d) }| / |S|        (0 when S is empty)

So the penalty *grows* with each additional same-partner item (1/1, then 2/2 only if every
prior pick was that partner, etc.), progressively discouraging one partner from dominating —
the property a binary flag cannot express.

Ties (equal MMR) are broken **deterministically** by raw fused score, then product_id, so
the output never depends on candidate iteration order.

Why this is an *alternative*, not the default (vs. ConstrainedRanker):
- **Soft penalty, not a hard guarantee.** MMR only *trades off* relevance vs diversity via
  λ. With a tight cluster of fused scores, min-max scaling compresses relevance into a narrow
  band, so the ``(1 − λ)`` redundancy penalty can dominate and a weaker item from another
  partner can jump in. ConstrainedRanker's hard per-partner *cap* bounds exposure by design.
- **Cost.** Greedy selection is O(N·K) (re-scan per slot) vs the constrained strategy's
  O(N log N) single sort — negligible here, but it matters at scale.
These trade-offs are exactly what an A/B comparison in the evaluation harness would measure.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.retrieval.ranking._common import price_per_unit
from app.retrieval.ranking.base import Ranker
from app.retrieval.types import Candidate, Sort

# Relevance/diversity trade-off. 0.7 leans toward relevance.
LAMBDA = 0.7


class MmrRanker(Ranker):
    def __init__(self, *, lambda_: float = LAMBDA) -> None:
        self._lambda = lambda_

    def rank(
        self, candidates: Sequence[Candidate], *, top_k: int, sort: Sort = Sort.RELEVANCE
    ) -> list[uuid.UUID]:
        if not candidates:
            return []

        relevance = _min_max_scaled({c.product_id: c.fused_score for c in candidates})
        remaining = list(candidates)
        selected: list[Candidate] = []

        while remaining and len(selected) < top_k:
            best, best_key = None, None
            for cand in remaining:
                # Graded redundancy: share of already-selected items from this partner, so
                # each additional same-partner pick is penalised more than the last.
                same_partner = sum(1 for s in selected if s.partner == cand.partner)
                redundancy = same_partner / len(selected) if selected else 0.0
                mmr = self._lambda * relevance[cand.product_id] - (1 - self._lambda) * redundancy
                # Deterministic tie-break: MMR, then raw relevance, then id — never iteration order.
                key = (mmr, cand.fused_score, cand.product_id.int)
                if best_key is None or key > best_key:
                    best, best_key = cand, key
            selected.append(best)
            remaining.remove(best)

        if sort is Sort.PRICE_LOW:
            selected.sort(key=price_per_unit)

        return [c.product_id for c in selected]


def _min_max_scaled(scores: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    """Scale scores to [0, 1] so relevance is comparable to the 0/1 similarity term."""
    values = scores.values()
    lo, hi = min(values), max(values)
    if hi == lo:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}
