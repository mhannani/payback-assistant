"""Constrained re-ranking — the default strategy.

Relevance is primary; fairness is a bounded, secondary constraint. This is the fix for
the per-source-normalization bug (a lone weak item in a sparse partner being promoted to
the top of its group). See docs/decisions/0002-fair-cross-partner-ranking.md.

Precision (keeping irrelevant items out of the candidate set at all) is NOT this ranker's
job — it is owned upstream by the CandidateFilter (see app/retrieval/filtering/), which
drops the noise tail before fusion. By the time candidates reach this ranker they are all
relevant; the ranker only decides *order* and *fair exposure* among them.

Algorithm
---------
Let ``rrf(d)`` be a candidate's fused relevance score (higher = better).

1. **Relevance baseline.** Consider candidates in descending ``rrf`` order — the raw fused
   score, with no normalization (normalization is what introduced the bug).

2. **Per-partner exposure cap.** No partner may take more than

       cap = ceil(top_k · MAX_PARTNER_SHARE)

   of the ``top_k`` slots (e.g. share 0.6 → at most 60 %). Greedy selection rule:

       pick d* = argmax_{ d : count[partner(d)] < cap } rrf(d)

   repeat until ``top_k`` are chosen or no eligible candidate remains.

3. **Back-fill.** If the cap leaves fewer than ``top_k`` chosen while candidates remain,
   fill the rest by global ``rrf`` order (so we never return fewer than available).

4. **Sort re-rank.** ``Sort.PRICE_LOW`` re-orders the *already-selected* set by ascending
   price-per-unit. It changes display order within the relevant set; it cannot pull an
   unselected (less relevant) item in — so relevance gates membership, price only reshuffles.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from collections.abc import Sequence

from app.retrieval.ranking._common import price_per_unit
from app.retrieval.ranking.base import Ranker
from app.retrieval.types import Candidate, Sort

# At most this share of the top_k may come from one partner (diversity without quotas).
MAX_PARTNER_SHARE = 0.6


class ConstrainedRanker(Ranker):
    def __init__(self, *, max_partner_share: float = MAX_PARTNER_SHARE) -> None:
        self._max_partner_share = max_partner_share

    def rank(
        self, candidates: Sequence[Candidate], *, top_k: int, sort: Sort = Sort.RELEVANCE
    ) -> list[uuid.UUID]:
        if not candidates:
            return []

        by_relevance = sorted(candidates, key=lambda c: c.fused_score, reverse=True)
        cap = max(1, math.ceil(top_k * self._max_partner_share))

        selected: list[Candidate] = []
        counts: dict = defaultdict(int)

        # Pass 1: relevance order, honouring the per-partner cap.
        for cand in by_relevance:
            if len(selected) >= top_k:
                break
            if counts[cand.partner] >= cap:
                continue
            selected.append(cand)
            counts[cand.partner] += 1

        # Pass 2: back-fill any remaining slots by global relevance (ignore the cap) so we
        # never under-fill when a partner's quota blocked candidates.
        if len(selected) < top_k:
            chosen = {c.product_id for c in selected}
            for cand in by_relevance:
                if len(selected) >= top_k:
                    break
                if cand.product_id not in chosen:
                    selected.append(cand)

        if sort is Sort.PRICE_LOW:
            selected.sort(key=price_per_unit)  # re-order the relevant set by value

        return [c.product_id for c in selected]
