"""BigQuery vector-index tests — hermetic. The BigQuery client is mocked, so the VECTOR_SEARCH
wiring (query build, parameter binding, candidate filtering) is exercised without GCP."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.config import Settings
from app.retrieval.base import backend_capabilities
from app.retrieval.filtering.none import NoFilter
from app.retrieval.types import RetrievalCapability
from app.retrieval.vector_index import BigQueryVectorIndex
from app.shared.partner import PartnerSlug

_IDS = [uuid.uuid4() for _ in range(3)]


class _FakeEmbedder:
    model_id = "openai:text-embedding-3-small"
    dimension = 1536


def _index(returned_ids: list[uuid.UUID]) -> tuple[BigQueryVectorIndex, MagicMock]:
    idx = BigQueryVectorIndex(
        Settings(vertexai_project="proj", bigquery_dataset="payback_vectors", bigquery_table="products"),
        _FakeEmbedder(),
    )
    fake_client = MagicMock()
    fake_client.query.return_value.result.return_value = [
        {"product_id": str(pid), "distance": 0.2 + i * 0.05} for i, pid in enumerate(returned_ids)
    ]
    idx._client = fake_client  # bypass the lazy real-client build
    return idx, fake_client


async def test_vector_search_returns_filtered_ids() -> None:
    idx, _ = _index(_IDS)
    ids = await idx.candidates(
        [0.1] * 1536, "openai:text-embedding-3-small", candidate_filter=NoFilter(), session=MagicMock()
    )
    assert ids == _IDS  # parsed from the mocked VECTOR_SEARCH result, filter passed through


async def test_query_binds_vector_and_filters_as_parameters() -> None:
    idx, client = _index(_IDS)
    await idx.candidates(
        [0.1] * 1536,
        "openai:text-embedding-3-small",
        candidate_filter=NoFilter(),
        session=MagicMock(),
        partner=PartnerSlug.DM,
        require_tags=["organic"],
    )
    # The query vector + filters are bound as parameters (never string-interpolated into SQL).
    sql, kwargs = client.query.call_args[0][0], client.query.call_args[1]
    param_names = {p.name for p in kwargs["job_config"].query_parameters}
    assert {"qvec", "model_id", "partner", "tags"} <= param_names
    assert "@qvec" in sql and "VECTOR_SEARCH" in sql


async def test_empty_result_returns_empty() -> None:
    idx, _ = _index([])
    ids = await idx.candidates(
        [0.1] * 1536, "m", candidate_filter=NoFilter(), session=MagicMock()
    )
    assert ids == []


def test_both_backends_are_hybrid() -> None:
    # GCP is BigQuery (semantic) + Postgres (lexical), so both backends advertise both arms.
    hybrid = frozenset({RetrievalCapability.VECTOR, RetrievalCapability.FULLTEXT})
    assert backend_capabilities("pgvector") == hybrid
    assert backend_capabilities("bigquery") == hybrid
    assert backend_capabilities("unknown") == frozenset()
