"""Unit tests for the candidate-filter strategies (no DB)."""

from __future__ import annotations

import uuid

import pytest

from app.retrieval.filtering import get_candidate_filter
from app.retrieval.filtering.absolute import AbsoluteCeilingFilter
from app.retrieval.filtering.autocut import AutoCutFilter
from app.retrieval.filtering.none import NoFilter
from app.retrieval.filtering.relative import RelativeThresholdFilter
from app.retrieval.filtering.base import ScoredCandidate


def _c(distance: float) -> ScoredCandidate:
    return ScoredCandidate(product_id=uuid.uuid4(), distance=distance)


# Models the real "günstige Windeln" shape: 4 close diapers, then a noise floor ~0.61.
DIAPERS = [_c(d) for d in (0.34, 0.41, 0.49, 0.50)]
NOISE = [_c(d) for d in (0.61, 0.62, 0.64, 0.66)]
POLLUTED = DIAPERS + NOISE


def test_none_keeps_everything() -> None:
    assert len(NoFilter().filter(POLLUTED)) == len(POLLUTED)


def test_absolute_keeps_only_within_ceiling() -> None:
    kept = AbsoluteCeilingFilter(ceiling=0.50).filter(POLLUTED)
    assert {c.distance for c in kept} == {0.34, 0.41, 0.49, 0.50}  # the diapers, no noise


def test_absolute_returns_empty_when_no_good_match() -> None:
    # A query whose best match is itself worse than the ceiling → honest "nothing relevant".
    assert AbsoluteCeilingFilter(ceiling=0.50).filter(NOISE) == []


def test_autocut_cuts_at_the_largest_gap() -> None:
    # The 0.50 → 0.61 jump is the biggest gap, so only the diapers survive.
    kept = AutoCutFilter().filter(POLLUTED)
    assert {round(c.distance, 2) for c in kept} == {0.34, 0.41, 0.49, 0.50}


def test_autocut_misfires_on_a_smooth_distribution() -> None:
    # Documents the fragility from the docstring: with no clear cliff (a smooth ramp where
    # the largest gap is NOT the signal/noise boundary), AutoCut cuts in the wrong place.
    # Here the biggest gap is the first (0.30→0.44), so it keeps only the single best item
    # and drops genuine matches — whereas the absolute ceiling keeps the right set.
    smooth = [_c(d) for d in (0.30, 0.44, 0.52, 0.60, 0.68)]
    autocut_kept = AutoCutFilter().filter(smooth)
    assert {round(c.distance, 2) for c in autocut_kept} == {0.30}  # over-tight misfire
    absolute_kept = AbsoluteCeilingFilter(ceiling=0.50).filter(smooth)
    assert {round(c.distance, 2) for c in absolute_kept} == {0.30, 0.44}  # the real matches


def test_relative_fails_when_best_is_excellent() -> None:
    # Documents the failure mode: best 0.19 → band ≤ 0.285 cuts genuine matches at 0.31+.
    cands = [_c(0.19), _c(0.31), _c(0.40)]  # all real, just less close
    kept = RelativeThresholdFilter(tolerance=0.5).filter(cands)
    assert len(kept) == 1  # only the best survives — the over-tight behaviour we avoid


def test_factory_default_is_absolute() -> None:
    assert isinstance(get_candidate_filter(), AbsoluteCeilingFilter)


def test_factory_unknown_strategy_raises() -> None:
    with pytest.raises(ValueError, match="unknown filter strategy"):
        get_candidate_filter("nope")
