"""Reciprocal Rank Fusion — merge several ranked id lists into one.

Fusion combines the hybrid arms (vector + full-text) into a single ranking. It works on
ranked id lists, never on SQL, so it is reused unchanged by any backend (pgvector today,
a warehouse like BigQuery later) — only candidate *generation* is engine-specific.

Why RRF is implemented here rather than pulled from a library (e.g. ``ranx``): RRF is a
one-line published formula, and ``ranx`` is built for offline IR *evaluation/benchmarking*
— it pulls in a heavy JIT dependency (Numba) and works on ``Run`` objects loaded from
TREC files, which would mean converting our id lists to/from its format on every request.
For fusing two short lists inside a latency-sensitive, "lightweight" serverless service,
that is the wrong tool. ``ranx`` would earn its place in a separate offline evaluation
harness (nDCG/MAP across many runs), not in the request path.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence

# Standard Reciprocal Rank Fusion constant (Cormack et al., SIGIR 2009): dampens how
# quickly a candidate's contribution decays with its rank. 60 is the field default.
RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[uuid.UUID]],
    *,
    k: int = RRF_K,
) -> dict[uuid.UUID, float]:
    """Fuse ranked id lists into one id→score map (higher = better).

    Each list contributes ``1 / (k + rank)`` for an id at its 0-based ``rank``. Scoring by
    *rank* (not raw score) means the lists' incomparable scales — cosine distance vs.
    ``ts_rank`` — never need reconciling, and ids that rank well in several lists accumulate
    the most, rewarding agreement between the arms.
    """
    scores: dict[uuid.UUID, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked):
            scores[item_id] += 1.0 / (k + rank + 1)
    return dict(scores)
