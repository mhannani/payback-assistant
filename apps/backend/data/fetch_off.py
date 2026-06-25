"""Fetch real products from the Open Food Facts public API and snapshot them.

This is a BUILD-TIME tool, run occasionally by a developer to refresh the catalog
snapshot — NOT part of the request or seed path. Its output
(``data/catalogs/dm.json`` and ``edeka.json``) is committed, so the seeder and the
demo run fully offline and reproducibly, with no live API dependency.

Each partner is snapshotted in its OWN raw shape — different field names, price
formats, and units — to mirror how three real partner feeds would actually differ.
The partner adapters (``data/adapters/``) are what normalize these disparate shapes
into one canonical product at load time; that normalization is the ingestion step.

Open Food Facts data is open (ODbL); we keep image URLs (not image bytes). Real data
is messy, so we clean as we go: prefer the German product name, take the first
reasonable category, drop entries without a name or image, and synthesise a plausible
retail price (OFF is a food database and carries none).
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any

import httpx

from app.shared.partner import PartnerSlug

OUTPUT_DIR = Path(__file__).parent / "catalogs"
_API = "https://world.openfoodfacts.org/cgi/search.pl"
_FIELDS = (
    "product_name,product_name_de,generic_name,brands,categories,"
    "image_front_url,quantity,code,labels,labels_tags"
)
_PRICE_SEED = 7  # deterministic synthetic prices for a stable snapshot
_MAX_RETRIES = 4  # transient-failure tolerance for the public OFF API

# Each OFF-backed partner is a set of search terms matching its assortment.
_PARTNER_QUERIES: dict[PartnerSlug, list[str]] = {
    # dm — drugstore / personal care: low price, high frequency.
    PartnerSlug.DM: ["shampoo", "zahnpasta", "duschgel", "handcreme", "windeln", "deo"],
    # EDEKA — groceries / fresh: pantry + produce staples.
    PartnerSlug.EDEKA: ["spaghetti", "tomaten passata", "olivenöl", "kaffee", "müsli", "schokolade"],
}
_PARTNER_PRICE_RANGE: dict[PartnerSlug, tuple[int, int]] = {
    PartnerSlug.DM: (95, 899),       # €0.95 – €8.99
    PartnerSlug.EDEKA: (49, 1499),   # €0.49 – €14.99
}


def _clean_category(raw: str | None) -> str | None:
    """Pick the first human-readable category from OFF's messy multi-value string."""
    if not raw:
        return None
    first = raw.split(",")[0].strip()
    # OFF sometimes prefixes language tags like 'de:Vollkorn' — strip them.
    return first.split(":", 1)[-1].strip() or None


def _best_name(p: dict) -> str | None:
    name = (p.get("product_name_de") or p.get("product_name") or "").strip()
    return name or None


def _search(client: httpx.Client, term: str, per_query: int) -> list[dict]:
    """Run one OFF search with retry/backoff. Returns [] if it keeps failing.

    The public OFF API is occasionally rate-limited / flaky (503s), so a build
    snapshot must tolerate a transient failure on a single query rather than abort
    the whole catalog. We back off and, if a query is hopeless, skip it.
    """
    params = {
        "search_terms": term,
        "tagtype_0": "countries",
        "tag_contains_0": "contains",
        "tag_0": "germany",
        "page_size": per_query,
        "json": 1,
        "fields": _FIELDS,
    }
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.get(_API, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json().get("products", [])
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            wait = 2 ** attempt
            print(f"  '{term}' attempt {attempt + 1}/{_MAX_RETRIES} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    print(f"  '{term}' skipped after {_MAX_RETRIES} attempts")
    return []


def _common_fields(p: dict) -> dict[str, Any] | None:
    """Extract the OFF fields both partners use, or None if the row is unusable."""
    name = _best_name(p)
    image = p.get("image_front_url")
    code = p.get("code")
    if not name or not image or not code:
        return None  # real data is incomplete — skip unusable rows
    return {
        "name": name[:255],
        "image": image,
        "code": code,
        "brand": (p.get("brands") or "").split(",")[0].strip() or None,
        "category": _clean_category(p.get("categories")),
        "quantity": (p.get("quantity") or "").strip() or None,
        # OFF's canonical dietary/label tags (e.g. 'en:organic', 'en:vegan'); the
        # adapter normalizes these into the product's `tags` for structured filtering.
        "labels_tags": p.get("labels_tags", []),
    }


def _emit_dm_raw(f: dict, term: str, price_cents: int) -> dict[str, Any]:
    """dm's raw feed shape: German keys, euro float price, pack size string."""
    return {
        "title": f["name"],
        "marke": f["brand"],
        "pack_size": f["quantity"],
        "price_eur": round(price_cents / 100, 2),
        "dm_category": f["category"],
        "bild_url": f["image"],
        "dm_gtin": f["code"],
        "labels_tags": f["labels_tags"],
        "quelle_suchbegriff": term,
    }


def _emit_edeka_raw(f: dict, term: str, price_cents: int) -> dict[str, Any]:
    """EDEKA's raw feed shape: comma-decimal price string, weight, label tags."""
    return {
        "name": f["name"],
        "hersteller": f["brand"],
        "weight": f["quantity"],
        "price": f"{price_cents // 100},{price_cents % 100:02d}",
        "kategorie": f["category"],
        "img": f["image"],
        "ean": f["code"],
        "labels_tags": f["labels_tags"],
        "suchwort": term,
    }


_PARTNER_EMITTERS = {
    PartnerSlug.DM: _emit_dm_raw,
    PartnerSlug.EDEKA: _emit_edeka_raw,
}


def _fetch_partner(
    client: httpx.Client, partner: PartnerSlug, per_query: int, rng: random.Random
) -> list[dict[str, Any]]:
    lo, hi = _PARTNER_PRICE_RANGE[partner]
    emit = _PARTNER_EMITTERS[partner]
    seen: set[str] = set()
    records: list[dict[str, Any]] = []

    for term in _PARTNER_QUERIES[partner]:
        time.sleep(1.0)  # be polite to the public API between queries
        for p in _search(client, term, per_query):
            fields = _common_fields(p)
            if fields is None or fields["code"] in seen:
                continue
            seen.add(fields["code"])
            records.append(emit(fields, term, rng.randint(lo, hi)))
    return records


def fetch(per_query: int = 15) -> dict[PartnerSlug, list[dict[str, Any]]]:
    """Fetch and clean catalogs for the OFF-backed partners (dm, edeka), in raw shape."""
    rng = random.Random(_PRICE_SEED)
    out: dict[PartnerSlug, list[dict[str, Any]]] = {}
    with httpx.Client(headers={"User-Agent": "payback-assistant/0.1"}) as client:
        for partner in _PARTNER_QUERIES:
            out[partner] = _fetch_partner(client, partner, per_query, rng)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot real products from Open Food Facts.")
    parser.add_argument("--per-query", type=int, default=15)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    catalogs = fetch(args.per_query)
    for partner, records in catalogs.items():
        if not records:
            raise SystemExit(
                f"{partner.value}: OFF returned no usable products — refusing to write an "
                "empty catalog. The API may be down; try again."
            )
        path = OUTPUT_DIR / f"{partner.value}.json"
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print(f"{partner.value}: wrote {len(records)} products → {path}")


if __name__ == "__main__":
    main()
