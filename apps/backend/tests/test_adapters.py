"""Adapter tests: the ingestion step that normalizes disparate feeds to one shape.

Pure (no DB, no network): they exercise the value normalization and run every
committed raw record through its adapter to prove the whole catalog ingests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.shared.partner import PartnerSlug
from data.adapters import get_adapter
from data.adapters.normalize import (
    euros_to_cents,
    german_price_to_cents,
    normalize_tags,
    parse_quantity,
)

CATALOG_DIR = Path(__file__).resolve().parent.parent / "data" / "catalogs"


# ── Value normalization ─────────────────────────────────────────────────────


def test_euros_to_cents() -> None:
    assert euros_to_cents(4.26) == 426
    assert euros_to_cents(0.0) == 0


def test_german_comma_price_to_cents() -> None:
    assert german_price_to_cents("5,06") == 506
    assert german_price_to_cents("1.234,50") == 123450  # thousands dot + decimal comma


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("700 g", (700, None)),
        ("500g", (500, None)),  # real OFF data omits the space
        ("1 kg", (1000, None)),  # pint converts to the base unit
        ("300 ml", (None, 300)),
        ("1,5 l", (None, 1500)),  # decimal comma + litre → millilitres
        ("6 x 1,5l", (None, 1500)),  # multi-pack prefix stripped
        ("250 G", (250, None)),  # case-insensitive
        ("1 Stück", (None, None)),  # a count is neither mass nor volume
        ("XL", (None, None)),  # garbage degrades gracefully
        (None, (None, None)),
    ],
)
def test_parse_quantity(text: str | None, expected: tuple[int | None, int | None]) -> None:
    assert parse_quantity(text) == expected


def test_normalize_tags() -> None:
    assert normalize_tags(["en:organic", "en:vegan"]) == ["organic", "vegan"]
    assert normalize_tags(["en:organic", "fr:bio", "en:organic"]) == ["organic"]  # en-only, de-duped
    assert normalize_tags(None) == []


# ── Per-partner mapping ─────────────────────────────────────────────────────


def test_dm_maps_euro_float_price_and_size() -> None:
    raw = {"title": "Shampoo", "marke": "Cien", "price_eur": 4.26, "pack_size": "300 ml", "bild_url": "x", "dm_gtin": "1"}
    rec = get_adapter(PartnerSlug.DM).to_canonical(raw)
    assert rec["partner"] is PartnerSlug.DM
    assert rec["price_cents"] == 426
    assert rec["volume_ml"] == 300 and rec["weight_g"] is None


def test_edeka_maps_comma_price_weight_and_tags() -> None:
    raw = {"name": "Tomaten", "hersteller": "Cirio", "price": "5,06", "weight": "700 g", "labels_tags": ["en:organic"], "img": "x", "ean": "1"}
    rec = get_adapter(PartnerSlug.EDEKA).to_canonical(raw)
    assert rec["price_cents"] == 506
    assert rec["weight_g"] == 700 and rec["volume_ml"] is None
    assert rec["tags"] == ["organic"]


def test_amazon_keeps_asin_and_category_path_no_tags() -> None:
    raw = {"product_name": "Headphones", "brand": "Anker", "asin": "B08", "list_price": 39.99, "category_path": "Electronics > Audio", "image": "x", "rating": 4.5}
    rec = get_adapter(PartnerSlug.AMAZON).to_canonical(raw)
    assert rec["price_cents"] == 3999
    assert rec["attrs"]["source_id"] == "B08"
    assert rec["attrs"]["category_path"] == "Electronics > Audio"
    assert rec["tags"] == []  # general merchandise has no dietary labels


# ── Whole-catalog ingestion ─────────────────────────────────────────────────


@pytest.mark.parametrize("partner", list(PartnerSlug))
def test_every_committed_record_ingests(partner: PartnerSlug) -> None:
    """Every raw record in every committed catalog normalizes to a valid product."""
    raw_records = json.loads((CATALOG_DIR / f"{partner.value}.json").read_text())
    adapter = get_adapter(partner)
    assert raw_records, f"{partner.value} catalog is empty"
    for raw in raw_records:
        rec = adapter.to_canonical(raw)
        assert rec["partner"] is partner
        assert rec["name"]
        assert rec["price_cents"] > 0
        assert rec["currency"] == "EUR"
        assert isinstance(rec["tags"], list)
        # A product is never both a weight and a volume.
        assert not (rec["weight_g"] and rec["volume_ml"])
