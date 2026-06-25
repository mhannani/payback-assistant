"""Partner adapters: turn each partner's raw feed into one canonical product.

The three partner feeds are deliberately *disparate* — different field names, price
formats, units, and label schemes. A ``PartnerAdapter`` is the ingestion step that
harmonizes one partner's shape into the single ``ProductRecord`` the rest of the
system understands, so retrieval can rank across all partners on equal terms. Adding
a partner means adding one adapter.

This module holds only the contract (the ABC). Value-normalization helpers live in
``normalize.py``; each partner's concrete mapping lives in its own module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.shared.partner import PartnerSlug
from data.schema import ProductRecord, RawRecord


class PartnerAdapter(ABC):
    """Maps one partner's raw feed record into the canonical product shape."""

    partner: PartnerSlug

    @abstractmethod
    def to_canonical(self, raw: RawRecord) -> ProductRecord:
        """Normalize a single raw record into a ``ProductRecord``."""
