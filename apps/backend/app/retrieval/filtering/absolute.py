"""Absolute distance ceiling — the default candidate filter.

Keep only candidates whose raw cosine distance is within a fixed ceiling; drop the rest as
noise. This is the standard "minimum similarity" production tool (OpenSearch radial search,
Weaviate distance threshold).

Algorithm
---------
    keep = { c : c.distance ≤ CEILING }

Why an absolute ceiling (not a relative "distance ≤ best × factor"): a *relative* threshold
breaks at both extremes, which we verified on this catalog:
  - When the best match is excellent (shampoo, best ≈ 0.19) a relative band is too tight and
    cuts genuine results.
  - When the best match is itself poor (a query with no real match, e.g. "Anker" here,
    best ≈ 0.59) a relative band keeps that noise — "1.5× of a bad best is still bad".
An absolute ceiling fixes both: a query with no good match simply keeps (almost) nothing —
an honest "no relevant results" — while good matches always pass.

The default ceiling (0.60) is calibrated for THIS embedding model (OpenAI
text-embedding-3-small), not guessed — a distance sweep showed relevant matches falling ~0.36–0.58
and noise ~0.64+, so 0.60 sits in the gap; `make eval` re-derives it on a wider set. It is bound to
the model's cosine-distance scale, so it MUST be re-calibrated if the embedding provider changes. It
is configurable (``settings.filter_ceiling``) precisely so that re-tuning is a config change, not a
code change. It trades a little recall for precision — a borderline item in the noise band is dropped.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.retrieval.filtering.base import CandidateFilter, ScoredCandidate

class AbsoluteCeilingFilter(CandidateFilter):
    def __init__(self, ceiling: float) -> None:
        # The ceiling is owned by config (settings.filter_ceiling) — the single source of truth —
        # and threaded in by the factory, so it isn't duplicated as a default here.
        self._ceiling = ceiling

    def filter(self, candidates: Sequence[ScoredCandidate]) -> list[ScoredCandidate]:
        return [c for c in candidates if c.distance <= self._ceiling]
