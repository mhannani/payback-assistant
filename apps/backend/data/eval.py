"""Offline A/B evaluation of the retrieval stack.

Answers the question the pluggable strategies raise: *which* candidate-filter and *which*
ranker actually retrieve better? It runs a small set of labelled queries
(``data/eval_queries.json``) through every (filter × ranker) combination and scores each with
standard IR metrics (nDCG, Recall, MRR) via ``ranx`` — the right tool for OFFLINE evaluation
(it is kept out of the request path on purpose; see app/retrieval/fusion.py).

Relevance is defined by a name predicate per query, not by hardcoded ids, so the labels
survive a re-seed. Run it after `make seed && make embed`:

    make eval

Reading the output: higher nDCG@k / Recall@k / MRR is better. Because the catalog is tiny
the absolute numbers are illustrative, not a benchmark — the *relative* ordering of
strategies is the signal, and the same harness is how you'd re-tune `filter_ceiling` for a
new embedding model.
"""

from __future__ import annotations

import asyncio
import json
import re
from itertools import product
from pathlib import Path

from ranx import Qrels, Run, compare
from sqlalchemy import select

from app.config import Settings
from app.db.models import Product
from app.db.session import SessionFactory
from app.retrieval.factory import get_retriever

QUERIES_PATH = Path(__file__).parent / "eval_queries.json"

# The strategies to A/B. Every combination is evaluated, so each stage's effect is isolated.
FILTERS = ["absolute", "autocut", "relative", "none"]
RANKERS = ["constrained", "mmr", "zscore"]


def _matches(name: str, patterns: list[str]) -> bool:
    return any(re.search(p, name, re.IGNORECASE) for p in patterns)


async def build_qrels(spec: dict) -> Qrels:
    """Turn each query's name predicate into relevance judgments over the seeded catalog.

    A product is relevant (grade 1) when its name matches the query's ``relevant`` patterns
    and none of its ``irrelevant`` patterns. ranx needs at least one judged doc per query.
    """
    qrels = Qrels()
    async with SessionFactory() as session:
        rows = (await session.execute(select(Product.id, Product.name))).all()
    for q in spec["queries"]:
        relevant = {
            str(pid): 1
            for pid, name in rows
            if _matches(name, q["relevant"]) and not _matches(name, q.get("irrelevant", []))
        }
        if not relevant:
            raise SystemExit(
                f"Query {q['id']!r} has no relevant products in the catalog — "
                "fix the predicate or re-seed."
            )
        qrels.add(q_id=q["id"], doc_ids=list(relevant), scores=list(relevant.values()))
    return qrels


async def build_run(spec: dict, *, filter_strategy: str, ranking_strategy: str) -> Run:
    """Run every query through one (filter × ranker) combo and record its ranking."""
    settings = Settings(filter_strategy=filter_strategy, ranking_strategy=ranking_strategy)
    retriever = get_retriever(settings=settings)
    k = spec["k"]
    run = Run(name=f"{filter_strategy}+{ranking_strategy}")
    async with SessionFactory() as session:
        for q in spec["queries"]:
            hits = await retriever.search(session, q["query"], top_k=k)
            # ranx scores on rank order; a descending score per position encodes it.
            doc_ids = [str(h.product_id) for h in hits]
            scores = [1.0 / (rank + 1) for rank in range(len(doc_ids))]
            if doc_ids:
                run.add(q_id=q["id"], doc_ids=doc_ids, scores=scores)
    return run


async def main() -> None:
    spec = json.loads(QUERIES_PATH.read_text())
    k = spec["k"]
    qrels = await build_qrels(spec)

    runs = []
    for filter_strategy, ranking_strategy in product(FILTERS, RANKERS):
        runs.append(
            await build_run(
                spec, filter_strategy=filter_strategy, ranking_strategy=ranking_strategy
            )
        )

    metrics = [f"ndcg@{k}", f"recall@{k}", "mrr"]
    report = compare(qrels=qrels, runs=runs, metrics=metrics, max_p=0.05)
    print(f"\nA/B evaluation over {len(spec['queries'])} labelled queries (k={k}):\n")
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
