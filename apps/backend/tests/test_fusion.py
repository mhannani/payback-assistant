"""Unit tests for the engine-agnostic ranking helpers (no DB)."""

from __future__ import annotations

import uuid

import pytest

from app.retrieval.fusion import RRF_K, reciprocal_rank_fusion

A, B, C, D = (uuid.uuid4() for _ in range(4))


def test_rrf_scores_match_the_formula() -> None:
    # A is rank 0 in one list → 1/(k+1).
    scores = reciprocal_rank_fusion([[A, B], [C]])
    assert scores[A] == pytest.approx(1.0 / (RRF_K + 1))
    assert scores[B] == pytest.approx(1.0 / (RRF_K + 2))
    assert scores[C] == pytest.approx(1.0 / (RRF_K + 1))


def test_rrf_rewards_agreement_between_lists() -> None:
    # C appears in BOTH lists; A tops one list but is absent from the other. Agreement
    # across arms beats a single strong rank — so C outranks A even though A is a #1.
    vector = [A, C]
    fulltext = [B, C]
    scores = reciprocal_rank_fusion([vector, fulltext])
    assert scores[C] > scores[A]
    assert scores[C] > scores[B]


def test_rrf_is_rank_based_not_score_based() -> None:
    # Inputs are pure rank order — no scores involved — so fusion can't depend on the
    # arms' incomparable score scales.
    scores = reciprocal_rank_fusion([[A, B, C, D]])
    ranked = sorted(scores, key=lambda i: scores[i], reverse=True)
    assert ranked == [A, B, C, D]


def test_rrf_empty_input() -> None:
    assert reciprocal_rank_fusion([]) == {}
    assert reciprocal_rank_fusion([[], []]) == {}
