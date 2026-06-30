"""Shared helpers for the ranking strategies (package-internal).

Several rankers apply the same ``Sort`` re-ordering, so the price logic lives here once
rather than being copied into each strategy.
"""

from __future__ import annotations

from app.retrieval.types import Candidate, SearchHit

# Unit-kind ordering for the price sort key. The integer is NOT a preference — it only
# keeps the three price bases in separate buckets so they never compare against each other.
_WEIGHT, _VOLUME, _UNITLESS = 0, 1, 2


def price_per_unit(candidate: Candidate) -> tuple[int, float]:
    """Comparable price for "cheapest", as a (unit_kind, value) sort key.

    Sticker price misleads across sizes — a 1 L bottle at 400 ct (40 ct / 100 ml) is
    better value than a 200 ml bottle at 200 ct (100 ct / 100 ml). Normalizing to a unit
    makes "cheap" mean *value*, not just the smallest number on the label::

        value = price_cents / size * 100      (size in g or ml)

    WHY a tuple, not a bare float: cents-per-100 g, cents-per-100 ml, and raw cents live on
    three incomparable scales — 40 (ct/100 g of a food) and 40 (ct/100 ml of a drink) are
    the same number but not the same thing, and collapsing them onto one axis silently
    interleaves foods, drinks, and unitless items in a PRICE_LOW sort. Returning
    ``(unit_kind, value)`` sorts within each base and never across it, so "cheapest" only
    ever compares like with like. Items without a parseable size fall back to raw cents.
    """
    if candidate.weight_g:
        return (_WEIGHT, candidate.price_cents / candidate.weight_g * 100)
    if candidate.volume_ml:
        return (_VOLUME, candidate.price_cents / candidate.volume_ml * 100)
    return (_UNITLESS, float(candidate.price_cents))


def unit_price_from_hit(hit: SearchHit) -> tuple[str, int] | None:
    """A *displayable* unit price for a result — the same value the PRICE_LOW ranker sorts by, but
    for a public ``SearchHit`` and shaped for the wire.

    Returns ``(basis, cents)`` where ``basis`` is ``"per_100g"`` / ``"per_100ml"`` and ``cents`` is the
    price normalized to that 100-unit base (rounded to whole cents — the comparison metric, not the
    shelf price). Returns ``None`` for an item with no parseable size (e.g. a Kindle), where a unit
    price is meaningless. Shares ``price_per_unit``'s formula so the comparison the API shows and the
    order the ranker produces agree on what "value" means — one source of truth.
    """
    if hit.weight_g:
        return ("per_100g", round(hit.price_cents / hit.weight_g * 100))
    if hit.volume_ml:
        return ("per_100ml", round(hit.price_cents / hit.volume_ml * 100))
    return None
