"""Partner adapters — the ingestion layer that unifies disparate feeds.

``get_adapter(partner)`` returns the adapter that turns that partner's raw feed
record into the canonical product shape.
"""

from __future__ import annotations

from app.shared.partner import PartnerSlug
from data.adapters.amazon import AmazonAdapter
from data.adapters.base import PartnerAdapter
from data.adapters.dm import DmAdapter
from data.adapters.edeka import EdekaAdapter

_ADAPTERS: dict[PartnerSlug, PartnerAdapter] = {
    PartnerSlug.DM: DmAdapter(),
    PartnerSlug.EDEKA: EdekaAdapter(),
    PartnerSlug.AMAZON: AmazonAdapter(),
}


def get_adapter(partner: PartnerSlug) -> PartnerAdapter:
    """Return the adapter for a partner's raw feed."""
    return _ADAPTERS[partner]


__all__ = ["PartnerAdapter", "get_adapter"]
