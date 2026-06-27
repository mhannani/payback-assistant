"""Value-normalization helpers shared by the partner adapters.

Each partner quotes prices, sizes, and labels its own way; these turn them into the
representations the canonical model uses — integer euro-cents, base-unit sizes
(grams / millilitres), and clean tag strings — so no partner-specific format leaks
past ingestion. Real feeds are messy, so parsing never raises: an unparseable value
yields ``None`` (or an empty result) rather than blocking the whole catalog.
"""

from __future__ import annotations

import re

import pint
from babel.numbers import NumberFormatError, parse_decimal

# One process-wide registry (constructing it is relatively expensive).
_UREG = pint.UnitRegistry()

# Strip a leading multi-pack prefix like "6 x " / "2x" so pint sees a single quantity.
_PACK_PREFIX_RE = re.compile(r"^\s*\d+\s*[x×]\s*", re.IGNORECASE)


def euros_to_cents(value: float) -> int:
    """4.26 → 426. Rounds to the nearest cent."""
    return round(value * 100)


def german_price_to_cents(text: str) -> int:
    """German-formatted price string → cents. '5,06' → 506, '1.234,50' → 123450.

    Uses Babel's locale-aware decimal parsing (decimal comma, thousands dot) rather
    than hand-rolled string surgery, so unusual but valid German formats still parse.
    """
    try:
        amount = parse_decimal(text.strip(), locale="de_DE", strict=False)
    except (NumberFormatError, AttributeError) as exc:
        raise ValueError(f"unparseable German price: {text!r}") from exc
    return round(float(amount) * 100)


def parse_quantity(text: str | None) -> tuple[int | None, int | None]:
    """Parse a free-text size into (weight_g, volume_ml); the irrelevant one is None.

    '500 g' → (500, None); '1,5 l' → (None, 1500); '300ml' → (None, 300). Anything
    that isn't a mass or volume ('1 Stück', 'XL', None) → (None, None). Uses pint so
    any metric unit normalizes to the base unit; parsing failures degrade to None.
    """
    if not text:
        return None, None
    cleaned = _PACK_PREFIX_RE.sub("", text).strip().lower().replace(",", ".")
    try:
        quantity = _UREG.Quantity(cleaned)
    except (pint.PintError, ValueError, AttributeError):
        return None, None
    if not isinstance(quantity, pint.Quantity):  # a bare number has no unit
        return None, None
    if quantity.check("[mass]"):
        return round(quantity.to("gram").magnitude), None
    if quantity.check("[volume]"):
        return None, round(quantity.to("milliliter").magnitude)
    return None, None


# The dietary attributes a shopper actually filters or asks about ("do you prefer
# organic?"). Open Food Facts emits hundreds of label tags — most are packaging or
# marketing noise (green-dot, eco-emballages, fsc-mix, 1-for-the-planet, nutriscore-*,
# made-in-*). We keep only this curated set so `tags` stays a clean, queryable signal.
_CANONICAL_TAGS = frozenset(
    {
        "organic",
        "vegan",
        "vegetarian",
        "gluten-free",
        "no-gluten",
        "lactose-free",
        "no-lactose",
        "palm-oil-free",
        "no-added-sugar",
        "sugar-free",
        "fair-trade",
        "halal",
        "kosher",
    }
)


def normalize_tags(labels_tags: list[str] | None) -> list[str]:
    """Open Food Facts label tags → clean, canonical dietary tags.

    'en:organic' → 'organic'. Strips the language prefix, keeps only the curated
    dietary attributes (dropping packaging/marketing noise), and de-duplicates while
    preserving order.
    """
    if not labels_tags:
        return []
    seen: dict[str, None] = {}
    for tag in labels_tags:
        if tag.startswith("en:"):
            name = tag[3:].lower()
            if name in _CANONICAL_TAGS:
                seen.setdefault(name, None)
    return list(seen)


def compose_description(*parts: str | None) -> str:
    """Join the present fragments into one description for the embedder / FT index.

    e.g. compose_description(brand, name, category, size). Empty/None parts are
    dropped; the result ends with a period for clean sentence-like text.
    """
    present = [part for part in parts if part]
    return ". ".join(present) + "."
