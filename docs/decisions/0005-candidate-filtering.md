# 0005 — Candidate filtering: cut the vector noise tail before fusion

**Status:** Accepted · **Date:** 2026-06-28

## Context

A vector ANN search always returns the *nearest* N products — even when most are not
actually relevant. For "günstige Windeln" (cheap diapers) the four real diapers were
followed by an undifferentiated tail of "least-far" but irrelevant items (shower gel,
toothpaste, coffee). That noise caused a visible failure: when sorting by price, the cheap
*coffee* outranked the relevant *diapers*.

Measured distances for "günstige Windeln" (cosine, 0 = identical):

```
0.3431  Öko Windeln        ← real diaper
0.4134  Premium Windeln    ← real diaper
0.4948  Windeln gr.2       ← real diaper
─────── clear gap ───────
0.6118  Duschgel Herren    ← noise
0.6379  löslichen Kaffee   ← noise (coffee)
```

Two facts shaped the fix:
- **Raw cosine distance carries the signal** (real matches cluster low; noise sits on a
  ~0.6 floor), but the **post-fusion RRF score is compressed** (top diaper 0.0164 vs coffee
  0.0147 — ~10% apart) and cannot separate them. So filtering must happen on the **raw
  distance, in the vector arm, before fusion.**
- A **relative** threshold (`distance ≤ best × 1.5`) fails at both extremes (verified): it
  cuts genuine results when the best match is excellent (shampoo, best ≈ 0.19), and keeps
  noise when the best match is itself poor (a no-real-match query, best ≈ 0.59) — a band
  around a bad anchor is still bad.

## Decision

Introduce a **`CandidateFilter`** applied in the vector arm, on the raw cosine distance,
**before fusion**. The default is an **absolute distance ceiling**: keep candidates with
`distance ≤ CEILING`, drop the rest.

The ceiling is tuned to this embedding model from a labelled sweep, not guessed:

| ceiling | günstige Windeln | pasta dinner | shampoo | Anker (no real match) |
|--------:|:----------------:|:------------:|:-------:|:---------------------:|
| **0.50** | 3 rel, **0 noise** | 10 rel, **0 noise** | 5 rel, **0 noise** | **0 kept** (honest) |
| 0.55     | 3 rel, 0 noise   | 12 rel, **3 noise** | 5 rel, 0 noise | 0 kept |
| 0.60     | 3 rel, 0 noise   | 13 rel, **6 noise** | 5 rel, **1 noise** | **1 noise** |

**`CEILING = 0.50`** gives zero noise across all four query types while keeping every true
match, and correctly returns nothing for a query with no real match. It favours precision
over recall (a borderline item in the noise band may be dropped).

The filter governs **only the vector arm's vouching**. The keyword (full-text) arm is
independent, so an exact keyword/brand match still surfaces via fusion even if the vector
arm scored it as far — verified: "Anker" returns the real Anker products through the keyword
arm although they sit above the vector ceiling. This is the intended hybrid behaviour.

## Alternatives (kept as A/B strategies behind the interface)

Like the rankers, candidate filtering is a pluggable strategy (`app/retrieval/filtering/`),
so alternatives can be A/B-compared in the evaluation harness:
- **AutoCut** (`autocut.py`): cut at the largest distance *gap* (Weaviate's AutoCut).
  Parameter-free and adapts per query, but fragile when the distribution is smooth / has no
  gap (e.g. a no-match query) — the absolute ceiling handles that case better.
- **Relative threshold** (`relative.py`): kept to *document* the failure mode above; not the
  default.
- **None** (`none.py`): the no-cutoff baseline (the behaviour that exhibited the bug) — the
  control for A/B comparison.

## Consequences

- The "cheap coffee over diapers" failure is fixed at the source: noise never enters fusion.
- A query with no good match returns (near) nothing instead of confident garbage.
- One tuned parameter (the ceiling), justified by data, plus a clean A/B seam.
- The filter is engine-agnostic (operates on `(id, distance)` pairs), reused by any backend.

## References

- ANN returns the closest match even when it isn't a good match; production stores expose a
  similarity threshold / AutoCut — Weaviate, *Vector search*:
  <https://docs.weaviate.io/weaviate/concepts/search/vector-search>
- Distance (radial) thresholds in vector search — OpenSearch, *Vector radial search*:
  <https://opensearch.org/blog/vector-radial-search/>
