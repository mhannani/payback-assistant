"""The vector-search seam — the one part of retrieval that varies by backend.

Hybrid retrieval (semantic arm + German lexical arm, fused by RRF, hydrated from Postgres, ranked)
is invariant across deployments. The *only* thing that changes is **where the semantic arm runs**:
Postgres + pgvector locally and on AWS, BigQuery on GCP. So that — and only that — is abstracted
here as a ``VectorIndex``; :class:`~app.retrieval.hybrid.HybridRetriever` composes one of these with
the shared pipeline. This keeps "the vector store is pluggable" honest without duplicating the
hybrid orchestration per backend.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.embeddings import Embedder
from app.retrieval.filtering import CandidateFilter
from app.shared.partner import PartnerSlug


class VectorIndex(ABC):
    """A semantic (nearest-neighbour) index over the product embeddings."""

    @abstractmethod
    async def candidates(
        self,
        query_vector: Sequence[float],
        model_id: str,
        *,
        candidate_filter: CandidateFilter,
        session: AsyncSession,
        partner: PartnerSlug | None = None,
        require_tags: Sequence[str] | None = None,
        candidate_k: int = 50,
    ) -> list[uuid.UUID]:
        """Return product ids ranked by cosine closeness, with the noise tail filtered.

        ``session`` is the retriever's shared Postgres session — used by the Postgres index, ignored
        by a remote one (BigQuery has its own client). Passing it keeps the Postgres-side work
        (lexical arm, row hydration, and the pgvector arm) on a single connection.
        """


class PgVectorIndex(VectorIndex):
    """Semantic search via Postgres + pgvector (cosine over the HNSW index)."""

    async def candidates(
        self,
        query_vector: Sequence[float],
        model_id: str,
        *,
        candidate_filter: CandidateFilter,
        session: AsyncSession,
        partner: PartnerSlug | None = None,
        require_tags: Sequence[str] | None = None,
        candidate_k: int = 50,
    ) -> list[uuid.UUID]:
        from app.retrieval.pgvector import vector_candidates

        return await vector_candidates(
            session,
            query_vector,
            model_id,
            candidate_filter=candidate_filter,
            partner=partner,
            require_tags=require_tags,
            candidate_k=candidate_k,
        )


class BigQueryVectorIndex(VectorIndex):
    """Semantic search via BigQuery ``VECTOR_SEARCH`` (the GCP warehouse vector store)."""

    def __init__(self, settings: Settings, embedder: Embedder) -> None:
        self._project = settings.vertex_project
        self._dataset = settings.bigquery_dataset
        self._table = settings.bigquery_table
        self._embedder = embedder  # only for parity; model_id is passed per call
        self._client = None

    def _bq_client(self):
        """Lazily build the BigQuery client (local/keyless paths never reach here)."""
        if self._client is None:
            from google.cloud import bigquery

            self._client = bigquery.Client(project=self._project)
        return self._client

    async def candidates(
        self,
        query_vector: Sequence[float],
        model_id: str,
        *,
        candidate_filter: CandidateFilter,
        session: AsyncSession,  # noqa: ARG002 — unused: BigQuery uses its own client
        partner: PartnerSlug | None = None,
        require_tags: Sequence[str] | None = None,
        candidate_k: int = 50,
    ) -> list[uuid.UUID]:
        from google.cloud import bigquery

        from app.retrieval.filtering import ScoredCandidate

        base = f"`{self._project}.{self._dataset}.{self._table}`"
        # Pre-filter the base table (only this model's vectors; optional partner / required tags) by
        # wrapping it in a subquery, so VECTOR_SEARCH only ever scans eligible rows.
        where = ["embedding_model = @model_id"]
        params: list[object] = [
            bigquery.ArrayQueryParameter("qvec", "FLOAT64", list(query_vector)),
            bigquery.ScalarQueryParameter("model_id", "STRING", model_id),
            bigquery.ScalarQueryParameter("top_k", "INT64", candidate_k),
        ]
        if partner is not None:
            where.append("partner = @partner")
            params.append(bigquery.ScalarQueryParameter("partner", "STRING", partner.value))
        if require_tags:
            where.append(
                "(SELECT COUNT(*) FROM UNNEST(@tags) t WHERE t IN UNNEST(tags)) = ARRAY_LENGTH(@tags)"
            )
            params.append(bigquery.ArrayQueryParameter("tags", "STRING", list(require_tags)))

        sql = f"""
        SELECT base.product_id AS product_id, distance
        FROM VECTOR_SEARCH(
          (SELECT * FROM {base} WHERE {" AND ".join(where)}),
          'embedding',
          (SELECT @qvec AS embedding),
          top_k => @top_k,
          distance_type => 'COSINE'
        )
        ORDER BY distance
        """
        job = self._bq_client().query(
            sql, job_config=bigquery.QueryJobConfig(query_parameters=params)
        )
        scored = [
            ScoredCandidate(product_id=uuid.UUID(str(row["product_id"])), distance=row["distance"])
            for row in job.result()
        ]
        return [c.product_id for c in candidate_filter.filter(scored)]
