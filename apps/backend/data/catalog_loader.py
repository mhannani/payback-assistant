"""Load the committed catalog snapshots from disk and normalize them.

The JSON files in ``data/catalogs/`` hold each partner's *raw* feed shape (dm/edeka
from the Open Food Facts snapshot, amazon curated). Loading runs each raw record
through its partner adapter, so the disparate feeds become one canonical shape here —
this is the ingestion step. It is pure and offline (no network), so the seeder and
the demo are reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.shared.partner import PartnerSlug
from data.adapters import get_adapter
from data.schema import ProductRecord

CATALOG_DIR = Path(__file__).parent / "catalogs"


def load_catalog(partner: PartnerSlug) -> list[ProductRecord]:
    """Load one partner's raw snapshot and normalize it to canonical records."""
    path = CATALOG_DIR / f"{partner.value}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Catalog snapshot missing: {path}. "
            "Run `python -m data.fetch_off` to (re)build the OFF-backed catalogs."
        )
    adapter = get_adapter(partner)
    raw_records = json.loads(path.read_text())
    return [adapter.to_canonical(raw) for raw in raw_records]


def load_all_catalogs() -> list[ProductRecord]:
    """Load every partner's catalog into one combined list."""
    records: list[ProductRecord] = []
    for partner in PartnerSlug:
        records.extend(load_catalog(partner))
    return records
