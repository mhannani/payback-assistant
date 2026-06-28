"""The ranker contract.

A ``Ranker`` decides the FINAL order of fused candidates and returns the top ids. It
owns every ordering concern — cross-partner fairness and the chosen ``Sort`` (e.g. price)
— so the retriever simply hands it candidates and reads back an order.

Strategies are interchangeable behind this interface (one today; others, e.g. MMR, can be
added as new implementations and A/B-compared in the evaluation harness). Ranking operates
on plain ``Candidate`` values, never on SQL, so it is reused by any backend.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.retrieval.types import Candidate, Sort


class Ranker(ABC):
    @abstractmethod
    def rank(
        self, candidates: Sequence[Candidate], *, top_k: int, sort: Sort = Sort.RELEVANCE
    ) -> list[uuid.UUID]:
        """Return the top ``top_k`` product ids in final order.

        ``sort`` selects the ordering among the relevant set (default relevance); it must
        never let a less-relevant item outrank a more-relevant one.
        """
