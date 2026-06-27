"""Checks on the committed catalog snapshots (no database, no network)."""

from app.shared.partner import PartnerSlug
from data.catalog_loader import load_all_catalogs, load_catalog


def test_every_partner_has_a_catalog() -> None:
    for partner in PartnerSlug:
        records = load_catalog(partner)
        assert records, f"{partner} catalog is empty"
        assert all(r["partner"] is partner for r in records)


def test_records_have_required_fields() -> None:
    for r in load_all_catalogs():
        assert r["name"]
        assert r["price_cents"] > 0
        assert r["currency"] == "EUR"
        assert isinstance(r["tags"], list)
        # Image is optional but, when present, must be a URL.
        if r["image_url"]:
            assert r["image_url"].startswith("http")


def test_amazon_catalog_is_long_tail_merchandise() -> None:
    amazon = load_catalog(PartnerSlug.AMAZON)
    # Each curated Amazon item keeps its ASIN (as source_id) + a category path.
    assert all({"source_id", "category_path"} <= r["attrs"].keys() for r in amazon)


def test_same_product_sold_by_multiple_partners_at_different_prices() -> None:
    # A Barilla spaghetti exists in both EDEKA and Amazon — the catalog must let
    # retrieval surface the cheaper partner for the same product.
    def barilla_spaghetti_prices(partner: PartnerSlug) -> list[int]:
        return [
            r["price_cents"]
            for r in load_catalog(partner)
            if r["brand"] == "Barilla" and "spaghetti" in r["name"].lower()
        ]

    edeka_prices = barilla_spaghetti_prices(PartnerSlug.EDEKA)
    amazon_prices = barilla_spaghetti_prices(PartnerSlug.AMAZON)
    assert edeka_prices, "expected a Barilla spaghetti in EDEKA"
    assert amazon_prices, "expected a Barilla spaghetti in Amazon"
    # Different partners price the same product differently — the point of the demo.
    assert set(edeka_prices) != set(amazon_prices)
