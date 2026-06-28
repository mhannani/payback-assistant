# 0002 — Fair cross-partner ranking: constrained re-ranking, not per-source normalization

**Status:** Accepted · **Date:** 2026-06-27

## Context

The brief's core challenge is to "search/recommend across **disparate** catalogs."
Searching all partners at once, a larger or denser catalog can dominate the result list
purely by contributing more candidates. We need every partner to get a fair chance to
surface — **without sacrificing relevance**.

## What we tried first, and why it was wrong

The initial approach **min-max normalized the fused (RRF) scores within each partner**,
then sorted globally. This has a fatal flaw, which a live query exposed:

> Query *"günstige Windeln"* (cheap diapers). All relevant diapers were in **dm**
> (fused scores ≈ 0.0164–0.0143, a tight cluster). A weakly-relevant **coffee** was the
> **only** candidate from EDEKA (fused ≈ 0.0147, mid-pack globally). Per-partner min-max
> normalization mapped the lone coffee to **1.0** (min == max in its group), tying the
> best diaper — and a subsequent price boost pushed the coffee to **#1**.

Per-source min-max normalization **promotes the "best of a sparse/weak group" to a
perfect score**, destroying the global relevance signal. It treats "best of the worst"
as equal to "best of the best." It is also fragile in general: normalization depends on a
per-query score distribution and is sensitive to outliers and tiny lists.

There is a deeper irony: we use **RRF specifically because it avoids score-normalization
fragility** (it fuses by rank, not raw score). Layering per-source min-max *on top of* RRF
re-introduced the exact pitfall RRF was chosen to avoid.

## Decision

**Relevance is primary; fairness is a bounded, secondary re-ranking step — never a
normalization that can override relevance.**

1. **Global relevance baseline** — sort candidates by their raw **RRF** score. This alone
   already ranks the diapers above the weak coffee.
2. **Constrained re-ranking for fairness** — apply a **per-partner exposure cap** (no
   single partner may take more than a set share of the top-K) so a dominant catalog
   can't crowd others out.
3. **Relevance guardrail** — a candidate below a minimum relevance score is **not**
   used to satisfy a partner's exposure; an empty slot is filled by the next best *global*
   item instead. This guarantees a low-quality item from a small partner is never
   promoted above a high-quality item from a large partner.

This is the production pattern: rank by relevance first, then apply diversity/fairness as
a secondary, bounded constraint (cf. Maximal Marginal Relevance, and industrial
re-ranking that scores "primarily on relevance, secondarily on diversity").

Ranking is a **pluggable strategy** (`app/retrieval/ranking/`, one file per algorithm,
selected by `get_ranker`). `ConstrainedRanker` (relevance + per-partner cap + guardrail) is
the **default**; the alternatives below are implemented too, so they can be A/B-compared on
labelled queries in the evaluation harness rather than chosen by assertion.

## Alternatives (implemented, not the default)

- **Maximal Marginal Relevance (MMR)** (`mmr.py`): `λ·rel − (1−λ)·max_{d'∈S} sim(d,d')`,
  with `sim` = same-partner (Carbonell & Goldstein, 1998). Diversity-aware, but a *soft*
  penalty with no hard relevance floor — with compressed fused scores a low λ can surface a
  weaker item; chosen against as the default because it can't *guarantee* relevance-first.
- **Z-score standardization** (`zscore.py`): `z = (x − μ)/σ`. The statistically correct fix
  for the min-max pathology (a lone item gets a distribution-relative score, not a forced
  1.0). Not the default because it assumes a roughly Gaussian score distribution, while
  search relevance scores are skewed/long-tailed — so a rank-based method + bounded
  constraint is more robust here.

## Consequences

- Relevance can never be overridden by the fairness mechanism (the guardrail enforces it).
- Two tunables — the per-partner cap and the relevance threshold — are explicit and
  testable, not hidden magic.
- The ranking layer stays engine-agnostic (operates on scores + partners, no SQL), so it
  is reused unchanged by any retrieval backend.

## References

- Reciprocal Rank Fusion avoids score-normalization fragility by fusing on rank —
  OpenSearch, *Introducing reciprocal rank fusion for hybrid search*:
  <https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/>
- The score-normalization problem in hybrid retrieval — A. Chauzov,
  *Hybrid retrieval with reciprocal rank fusion*:
  <https://avchauzov.github.io/blog/2025/hybrid-retrieval-rrf-rank-fusion/>
- Result fusion & ranking strategies (normalization is distribution-sensitive) — APXML:
  <https://apxml.com/courses/advanced-vector-search-llms/chapter-3-hybrid-search-approaches/result-fusion-ranking-strategies>
- Relevance-primary, diversity-secondary re-ranking in production — *Methodologies for
  Improving Modern Industrial Recommender Systems*: <https://arxiv.org/pdf/2308.01204>
- Maximal Marginal Relevance (relevance/diversity trade-off): <https://aayushmnit.com/posts/2025-12-25-DiversityMMRPart1/DiversityMMRPart1.html>
