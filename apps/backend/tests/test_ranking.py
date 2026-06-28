"""Unit tests for the ranking strategies (no DB)."""

from __future__ import annotations

import uuid

import pytest

from app.retrieval.ranking import get_ranker
from app.retrieval.ranking.constrained import ConstrainedRanker
from app.retrieval.ranking.mmr import MmrRanker
from app.retrieval.ranking.zscore import ZScoreRanker
from app.retrieval.types import Candidate, Sort
from app.shared.partner import PartnerSlug

ALL_RANKERS = [ConstrainedRanker(), MmrRanker(), ZScoreRanker()]


def _cand(partner, fused, *, price=100, weight_g=None, volume_ml=None) -> Candidate:
    return Candidate(uuid.uuid4(), partner, fused, price, weight_g, volume_ml)


# ── Behaviour every strategy must satisfy ───────────────────────────────────


@pytest.mark.parametrize("ranker", ALL_RANKERS, ids=lambda r: type(r).__name__)
def test_relevance_first_lone_weak_item_not_promoted(ranker) -> None:
    # The original bug: 4 strongly-relevant items + 1 lone weak item in a sparse partner.
    # No strategy may rank the weak item first.
    strong = [_cand(PartnerSlug.DM, s) for s in (0.0164, 0.0161, 0.0159, 0.0156)]
    weak_lone = _cand(PartnerSlug.EDEKA, 0.0147)
    ranked = ranker.rank([*strong, weak_lone], top_k=5)
    assert ranked[0] != weak_lone.product_id


@pytest.mark.parametrize("ranker", ALL_RANKERS, ids=lambda r: type(r).__name__)
def test_empty_candidates(ranker) -> None:
    assert ranker.rank([], top_k=5) == []


@pytest.mark.parametrize("ranker", ALL_RANKERS, ids=lambda r: type(r).__name__)
def test_respects_top_k(ranker) -> None:
    cands = [_cand(PartnerSlug.DM, s) for s in (0.9, 0.8, 0.7, 0.6, 0.5)]
    assert len(ranker.rank(cands, top_k=3)) == 3


# ── ConstrainedRanker specifics (the default) ───────────────────────────────


def test_constrained_caps_a_dominant_partner() -> None:
    # dm floods candidates; the cap must leave room for amazon's best in the top-k.
    dm = [_cand(PartnerSlug.DM, s) for s in (0.9, 0.85, 0.8, 0.75, 0.7)]
    amazon = _cand(PartnerSlug.AMAZON, 0.65)
    ranked = ConstrainedRanker(max_partner_share=0.6).rank([*dm, amazon], top_k=5)
    partners = {c.product_id: c.partner for c in [*dm, amazon]}
    assert PartnerSlug.AMAZON in {partners[pid] for pid in ranked}


def test_constrained_cap_count_enforced_in_pass_one() -> None:
    # cap = ceil(5 * 0.6) = 3. With enough cross-partner candidates, pass-1 must hold dm
    # to 3 and fill the rest from other partners (not just "amazon appears somewhere").
    dm = [_cand(PartnerSlug.DM, s) for s in (0.99, 0.98, 0.97, 0.96, 0.95)]
    edeka = [_cand(PartnerSlug.EDEKA, s) for s in (0.50, 0.49)]
    cands = [*dm, *edeka]
    partners = {c.product_id: c.partner for c in cands}
    ranked = ConstrainedRanker(max_partner_share=0.6).rank(cands, top_k=5)
    counts = {p: 0 for p in PartnerSlug}
    for pid in ranked:
        counts[partners[pid]] += 1
    assert counts[PartnerSlug.DM] == 3  # capped, even though dm had the 5 best scores
    assert counts[PartnerSlug.EDEKA] == 2  # weaker cross-partner items filled the slots


def test_constrained_backfill_over_cap_when_no_alternative() -> None:
    # Only dm has candidates; the cap (3) would under-fill top_k=5, so pass-2 back-fills
    # the remaining 2 over-cap items by relevance — we never return fewer than available.
    dm = [_cand(PartnerSlug.DM, s) for s in (0.9, 0.8, 0.7, 0.6, 0.5)]
    ranked = ConstrainedRanker(max_partner_share=0.6).rank(dm, top_k=5)
    assert len(ranked) == 5  # full, despite only one partner and a 3-item cap


def test_constrained_price_low_sorts_relevant_set_by_value() -> None:
    # Among comparably-relevant items, PRICE_LOW prefers the better price-per-unit.
    big = _cand(PartnerSlug.EDEKA, 0.8, price=400, volume_ml=1000)  # 40 ct / 100 ml
    small = _cand(PartnerSlug.EDEKA, 0.8, price=200, volume_ml=200)  # 100 ct / 100 ml
    ranked = ConstrainedRanker().rank([big, small], top_k=2, sort=Sort.PRICE_LOW)
    assert ranked[0] == big.product_id


def test_constrained_price_low_excludes_cheap_irrelevant_before_resort() -> None:
    # The cheap item must be dropped during relevance selection (tight top_k), NOT pulled
    # to the front by the price re-sort — relevance gates membership, price only reorders.
    pricey_relevant = [
        _cand(PartnerSlug.DM, s, price=900, weight_g=100) for s in (0.9, 0.85, 0.8, 0.75)
    ]
    cheap_irrelevant = _cand(PartnerSlug.DM, 0.10, price=10, weight_g=100)  # cheapest, weakest
    ranked = ConstrainedRanker().rank(
        [*pricey_relevant, cheap_irrelevant], top_k=4, sort=Sort.PRICE_LOW
    )
    assert cheap_irrelevant.product_id not in ranked


def test_price_low_weight_branch_cheaper_per_100g_wins() -> None:
    cheap = _cand(PartnerSlug.DM, 0.8, price=100, weight_g=1000)  # 10 ct / 100 g
    dear = _cand(PartnerSlug.DM, 0.8, price=100, weight_g=100)  # 100 ct / 100 g
    ranked = ConstrainedRanker().rank([dear, cheap], top_k=2, sort=Sort.PRICE_LOW)
    assert ranked[0] == cheap.product_id


def test_price_low_unitless_fallback_uses_raw_cents() -> None:
    cheap = _cand(PartnerSlug.AMAZON, 0.8, price=500)  # no size → raw cents
    dear = _cand(PartnerSlug.AMAZON, 0.8, price=2000)
    ranked = ConstrainedRanker().rank([dear, cheap], top_k=2, sort=Sort.PRICE_LOW)
    assert ranked[0] == cheap.product_id


def test_price_low_does_not_interleave_unit_bases() -> None:
    # A weight item, a volume item, and an unitless item must not interleave on one scale:
    # the (unit_kind, value) key keeps each base in its own bucket. A genuinely cheap
    # unitless item (raw 5 ct) must not be buried by, nor bury, items in other bases.
    weight = _cand(PartnerSlug.DM, 0.8, price=100, weight_g=100)  # (0, 100.0)
    volume = _cand(PartnerSlug.EDEKA, 0.8, price=100, volume_ml=100)  # (1, 100.0)
    unitless = _cand(PartnerSlug.AMAZON, 0.8, price=5)  # (2, 5.0)
    ranked = ConstrainedRanker().rank(
        [unitless, volume, weight], top_k=3, sort=Sort.PRICE_LOW
    )
    # Bucketed by unit kind: all weight, then all volume, then all unitless.
    assert ranked == [weight.product_id, volume.product_id, unitless.product_id]


def test_price_low_tie_stability_keeps_relevance_order() -> None:
    # Equal price-per-unit → list.sort is stable, so the more-relevant item stays first.
    more_rel = _cand(PartnerSlug.DM, 0.9, price=100, weight_g=100)
    less_rel = _cand(PartnerSlug.DM, 0.5, price=100, weight_g=100)  # same 100 ct/100g
    ranked = ConstrainedRanker().rank([more_rel, less_rel], top_k=2, sort=Sort.PRICE_LOW)
    assert ranked == [more_rel.product_id, less_rel.product_id]


# ── MmrRanker specifics ──────────────────────────────────────────────────────


def test_mmr_redundancy_escalates_with_each_same_partner_pick() -> None:
    # Graded redundancy: a TIGHT relevance cluster (so the diversity term can matter) with
    # dm holding the top scores. After dm fills its early slots, the escalating same-partner
    # penalty must let a competitive other-partner item in — a binary one-shot flag (which
    # gives every dm-after-the-first the SAME penalty) would not escalate the same way.
    dm = [_cand(PartnerSlug.DM, s) for s in (1.00, 0.97, 0.94, 0.91)]
    others = [_cand(PartnerSlug.EDEKA, 0.90), _cand(PartnerSlug.AMAZON, 0.89)]
    cands = [*dm, *others]
    partners = {c.product_id: c.partner for c in cands}
    ranked = MmrRanker(lambda_=0.5).rank(cands, top_k=4)
    picked_partners = [partners[pid] for pid in ranked]
    # Not all four picks are dm — the escalating penalty pulled in another partner.
    assert picked_partners.count(PartnerSlug.DM) < 4


def test_mmr_is_deterministic_regardless_of_input_order() -> None:
    cands = [
        _cand(PartnerSlug.DM, 0.9),
        _cand(PartnerSlug.EDEKA, 0.8),
        _cand(PartnerSlug.AMAZON, 0.7),
    ]
    a = MmrRanker().rank(cands, top_k=3)
    b = MmrRanker().rank(list(reversed(cands)), top_k=3)
    assert a == b


# ── ZScoreRanker specifics ───────────────────────────────────────────────────


def test_zscore_all_equal_scores_falls_back_to_neutral() -> None:
    # σ == 0 (all scores equal) → z = 0 for every item, so it must not crash and must
    # return all of them (no min-max 1.0 pathology, no division by zero).
    cands = [_cand(PartnerSlug.DM, 0.5) for _ in range(3)]
    ranked = ZScoreRanker().rank(cands, top_k=3)
    assert len(ranked) == 3


# ── Factory ─────────────────────────────────────────────────────────────────


def test_factory_default_is_constrained() -> None:
    assert isinstance(get_ranker(), ConstrainedRanker)


def test_factory_unknown_strategy_raises() -> None:
    with pytest.raises(ValueError, match="unknown ranking strategy"):
        get_ranker("nope")
