"""Load the committed catalog snapshots from disk.

The JSON files in ``data/catalogs/`` are the source of truth for the product
data: dm/edeka come from the Open Food Facts snapshot (data/fetch_off.py), amazon
is a curated set. Loading is pure and offline — no network, so the seeder and the
demo are reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.shared.partner import PartnerSlug
from data.schema import ProductRecord

CATALOG_DIR = Path(__file__).parent / "catalogs"


def load_catalog(partner: PartnerSlug) -> list[ProductRecord]:
    """Load and validate one partner's catalog from its JSON snapshot."""
    path = CATALOG_DIR / f"{partner.value}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Catalog snapshot missing: {path}. "
            "Run `python -m data.fetch_off` to (re)build the OFF-backed catalogs."
        )
    raw = json.loads(path.read_text())
    records: list[ProductRecord] = []
    for row in raw:
        # Normalise the partner field to the typed enum so downstream code never
        # handles a stray string.
        row["partner"] = PartnerSlug(row["partner"])
        records.append(row)  # type: ignore[arg-type]
    return records


def load_all_catalogs() -> list[ProductRecord]:
    """Load every partner's catalog into one combined list."""
    records: list[ProductRecord] = []
    for partner in PartnerSlug:
        records.extend(load_catalog(partner))
    return records
