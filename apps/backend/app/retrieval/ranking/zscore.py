"""Z-score standardization — the statistically correct normalization alternative.

This is the principled version of the normalization that the first (buggy) attempt got
wrong. Instead of per-partner min-max — which forces a lone item to 1.0 (``min == max``)
and so promoted a weak "best-of-a-sparse-group" item — it standardizes scores to how many
standard deviations each sits from the mean.

Algorithm
---------
For the candidate scores ``x`` with mean ``μ`` and standard deviation ``σ``:

    z = (x − μ) / σ

Sort by ``z`` descending. A lone or weak item does not become "the maximum": it gets a
``z`` reflecting how far above average it actually is. When ``σ = 0`` (all scores equal,
or a single candidate) the score is undefined, so we fall back to ``z = 0`` (neutral) —
which is exactly why this avoids the min-max pathology (min-max would force 1.0 there).

We standardize over the **whole candidate set** (one global distribution), not per
partner: a global z-score keeps relevance comparable across partners, whereas a
per-partner z-score would re-introduce a version of the sparse-group problem.

(The productionized variant is Distribution-Based Score Fusion (DBSF, Qdrant), which
normalizes with the 3-sigma range, ``ŝ = (s − (μ − 3σ)) / 6σ``, before summing across
retrievers — the same idea, bounded to [0, 1] so a single outlier can't distort it.)

Why this is an *alternative*, not the default:
- **It assumes a Gaussian distribution.** ``(x − μ) / σ`` is only a meaningful comparison
  if scores are roughly bell-shaped — but search relevance scores (cosine, ts_rank) are
  typically long-tailed/skewed, so a parametric normalization is on shaky ground here.
- **Outlier-sensitive.** One very high score inflates ``σ`` and compresses everyone else's
  z toward 0, making the order unstable. Plain z-score (unlike DBSF) is unbounded.
The rank-based methods (RRF fusion, the constrained strategy) make NO distributional
assumption, which is why they are more robust for skewed e-commerce data — this strategy
is kept to show the statistical trade-off was evaluated, not just tried.
"""

from __future__ import annotations

import statistics
import uuid
from collections.abc import Sequence

from app.retrieval.ranking._common import price_per_unit
from app.retrieval.ranking.base import Ranker
from app.retrieval.types import Candidate, Sort


class ZScoreRanker(Ranker):
    def rank(
        self, candidates: Sequence[Candidate], *, top_k: int, sort: Sort = Sort.RELEVANCE
    ) -> list[uuid.UUID]:
        if not candidates:
            return []

        scores = [c.fused_score for c in candidates]
        mean = statistics.fmean(scores)
        # Population std dev; 0 when there is a single candidate or all scores are equal.
        stdev = statistics.pstdev(scores)

        def z(candidate: Candidate) -> float:
            return 0.0 if stdev == 0 else (candidate.fused_score - mean) / stdev

        selected = sorted(candidates, key=z, reverse=True)[:top_k]

        if sort is Sort.PRICE_LOW:
            selected = sorted(selected, key=price_per_unit)

        return [c.product_id for c in selected]
