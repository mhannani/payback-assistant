"""Fetch real products from the Open Food Facts public API and snapshot them.

This is a BUILD-TIME tool, run occasionally by a developer to refresh the
catalog snapshot — NOT part of the request or seed path. Its output
(``data/catalogs/dm.json`` and ``edeka.json``) is committed, so the seeder and
the demo run fully offline and reproducibly, with no live API dependency.

Open Food Facts data is open (ODbL); we keep image URLs (not image bytes).
Real data is messy, so we clean as we go: prefer the German product name, take
the first reasonable category, drop entries without a name or image, and
synthesise a plausible retail price (OFF is a food database and carries none).
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import httpx

from app.shared.partner import PartnerSlug
from data.schema import ProductRecord

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


def _build_description(
    *,
    brand: str | None,
    name: str,
    generic_name: str | None,
    category: str | None,
    quantity: str | None,
    labels: str | None,
) -> str:
    """Compose one description from the OFF fragments that exist.

    OFF has no single ready-made description, so we assemble brand + name +
    generic name ("what it is") + category + size + dietary labels into one
    string — more semantic signal for the embedder. Missing fragments (real
    OFF data is patchy) are skipped, and the generic name is dropped when it
    merely repeats the name. Mixed languages are fine: the multilingual embedder
    matches them to queries in any language.
    """
    parts: list[str] = []
    if brand:
        parts.append(brand)
    parts.append(name)
    if generic_name and generic_name.lower() not in name.lower():
        parts.append(generic_name)
    if category:
        parts.append(category)
    if quantity:
        parts.append(quantity)
    if labels:
        parts.append(labels)
    return ". ".join(parts) + "."


def _search(client: httpx.Client, term: str, per_query: int) -> list[dict]:
    """Run one OFF search with retry/backoff. Returns [] if it keeps failing.

    The public OFF API is occasionally rate-limited / flaky (503s), so a build
    snapshot must tolerate a transient failure on a single query rather than
    abort the whole catalog. We back off and, if a query is hopeless, skip it.
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


def _fetch_partner(
    client: httpx.Client, partner: PartnerSlug, per_query: int, rng: random.Random
) -> list[ProductRecord]:
    lo, hi = _PARTNER_PRICE_RANGE[partner]
    seen: set[str] = set()
    records: list[ProductRecord] = []

    for term in _PARTNER_QUERIES[partner]:
        time.sleep(1.0)  # be polite to the public API between queries
        for p in _search(client, term, per_query):
            name = _best_name(p)
            image = p.get("image_front_url")
            code = p.get("code")
            if not name or not image or not code or code in seen:
                continue  # real data is incomplete — skip unusable rows
            seen.add(code)

            brand = (p.get("brands") or "").split(",")[0].strip() or None
            category = _clean_category(p.get("categories"))
            quantity = (p.get("quantity") or "").strip() or None
            generic = (p.get("generic_name") or "").strip() or None
            labels = (p.get("labels") or "").strip() or None
            is_bio = any("organic" in t or "bio" in t for t in p.get("labels_tags", []))

            attrs: dict = {"off_code": code, "search_term": term}
            if category:
                attrs["category"] = category
            if quantity:
                attrs["quantity"] = quantity
            if partner is PartnerSlug.EDEKA:
                attrs["bio"] = is_bio

            records.append(
                ProductRecord(
                    partner=partner,
                    brand=brand,
                    name=name[:255],
                    description=_build_description(
                        brand=brand,
                        name=name,
                        generic_name=generic,
                        category=category,
                        quantity=quantity,
                        labels=labels,
                    ),
                    price_cents=rng.randint(lo, hi),
                    currency="EUR",
                    image_url=image,
                    attrs=attrs,
                )
            )
    return records


def fetch(per_query: int = 15) -> dict[PartnerSlug, list[ProductRecord]]:
    """Fetch and clean catalogs for the OFF-backed partners (dm, edeka)."""
    rng = random.Random(_PRICE_SEED)
    out: dict[PartnerSlug, list[ProductRecord]] = {}
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
        path = OUTPUT_DIR / f"{partner}.json"
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print(f"{partner}: wrote {len(records)} products → {path}")


if __name__ == "__main__":
    main()
