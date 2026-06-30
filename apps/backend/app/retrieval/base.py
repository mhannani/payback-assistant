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

from app.retrieval.types import RetrievalCapability, SearchHit, Sort
from app.shared.partner import PartnerSlug

# Retrieval is hybrid on every backend: the semantic arm is the configured vector store, the
# lexical arm is always Postgres German full-text. So both backends are {VECTOR, FULLTEXT}; the
# difference is only WHERE the semantic arm runs, not which arms exist.
_HYBRID = frozenset({RetrievalCapability.VECTOR, RetrievalCapability.FULLTEXT})
BACKEND_CAPABILITIES: dict[str, frozenset[RetrievalCapability]] = {
    "pgvector": _HYBRID,
    "bigquery": _HYBRID,
}


def backend_capabilities(backend: str) -> frozenset[RetrievalCapability]:
    """The retrieval arms a backend supports (empty for an unknown backend)."""
    return BACKEND_CAPABILITIES.get(backend, frozenset())


class Retriever(ABC):
    @property
    @abstractmethod
    def capabilities(self) -> frozenset[RetrievalCapability]:
        """Which retrieval arms this backend runs (e.g. {VECTOR, FULLTEXT} vs {VECTOR}).

        Backends differ in quality — Postgres is hybrid; a warehouse backend may be vector-only.
        Exposing that here (and on /config) makes the difference explicit, not a hidden surprise.
        """

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        partner: PartnerSlug | None = None,
        sort: Sort = Sort.RELEVANCE,
        require_tags: Sequence[str] | None = None,
        candidate_k: int = 50,
    ) -> list[SearchHit]:
        """Return the top ``top_k`` products for ``query``, ranked across partners.

        The retriever owns its own data access — no session/connection is passed in, keeping the
        contract independent of any one backend's storage engine. ``partner`` restricts to one
        catalog; ``require_tags`` keeps only products carrying all given tags; ``sort`` chooses the
        ordering among the relevant set; ``candidate_k`` is how many candidates each arm fetches.
        """
