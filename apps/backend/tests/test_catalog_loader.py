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
        # Image is optional but, when present, must be a URL.
        if r["image_url"]:
            assert r["image_url"].startswith("http")


def test_amazon_catalog_is_long_tail_merchandise() -> None:
    amazon = load_catalog(PartnerSlug.AMAZON)
    # Each curated Amazon item carries its ASIN + a category path.
    assert all({"asin", "category_path"} <= r["attrs"].keys() for r in amazon)
