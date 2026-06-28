"""The retriever contract.

A ``Retriever`` searches and ranks products across the partner catalogs for a query.
Implementations are interchangeable behind this interface, so the backend (pgvector
today, a warehouse like BigQuery later) is a config choice and the API/agent depend
only on the contract.

It is pure mechanism: ``search`` takes EXPLICIT options (filter to a partner, choose a
sort, require certain tags) and never parses intent from the raw text. Deciding those
options from a natural-language query is the intent agent's job (Task 2); the retriever
just executes the request, which keeps it deterministic and testable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.types import SearchHit, Sort
from app.shared.partner import PartnerSlug


class Retriever(ABC):
    @abstractmethod
    async def search(
        self,
        session: AsyncSession,
        query: str,
        *,
        top_k: int = 10,
        partner: PartnerSlug | None = None,
        sort: Sort = Sort.RELEVANCE,
        require_tags: Sequence[str] | None = None,
        candidate_k: int = 50,
    ) -> list[SearchHit]:
        """Return the top ``top_k`` products for ``query``, ranked across partners.

        ``partner`` restricts to one catalog; ``require_tags`` keeps only products
        carrying all given tags; ``sort`` chooses the ordering among the relevant set
        (default relevance). ``candidate_k`` is how many candidates each arm fetches
        before fusion.
        """
