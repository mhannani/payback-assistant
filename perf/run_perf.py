"""Load test the assistant: latency percentiles + cost per 1000 requests.

A thin HTTP *client* (sibling of ``demo/``) that drives ``POST /assist`` under concurrency to
answer the brief's optional performance question: does it scale, and what does it cost?

* **Latency** — every request is timed end to end; we report p50 / p95 / p99 and throughput.
* **Cost** — the API returns the LLM cost of each turn in its ``usage`` block (token counts from
  LangChain, priced by LiteLLM — see ``app/llm/cost.py``). We sum those real figures and scale to
  1000 requests. No hand-rolled pricing: the number is whatever LiteLLM charged.

The query mix is reused from ``demo/queries.json`` so the load reflects real intents (search,
route, vague→clarify). ``N`` is bounded and logged so a run is a few cents, not a surprise bill.

``make perf`` runs it in the api container against the local service (needs ``OPENAI_API_KEY`` set,
since it calls the real LLM); point ``--base-url`` at a deployed URL to test that instead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from statistics import median

import httpx

# Reuse the demo's representative query mix (mounted alongside perf/ in the container).
QUERIES_PATH = Path(__file__).resolve().parent.parent / "demo" / "queries.json"


def load_queries() -> list[str]:
    """The query strings to load-test with (the demo's labelled mix, queries only)."""
    return [q["query"] for q in json.loads(QUERIES_PATH.read_text())["queries"]]


async def _one_request(client: httpx.AsyncClient, query: str) -> tuple[float, float]:
    """Send one /assist request; return (latency_seconds, cost_usd_of_the_turn)."""
    start = time.perf_counter()
    resp = await client.post("/assist", json={"query": query})
    latency = time.perf_counter() - start
    resp.raise_for_status()
    usage = resp.json().get("usage") or {}
    return latency, float(usage.get("cost_usd", 0.0))


async def _run(base_url: str, total: int, concurrency: int) -> tuple[list[float], float]:
    """Fire ``total`` requests, at most ``concurrency`` in flight; collect latencies + total cost."""
    queries = load_queries()
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    total_cost = 0.0

    async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:

        async def worker(i: int) -> None:
            nonlocal total_cost
            async with sem:
                latency, cost = await _one_request(client, queries[i % len(queries)])
            latencies.append(latency)
            total_cost += cost

        await asyncio.gather(*(worker(i) for i in range(total)))

    return latencies, total_cost


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile (e.g. pct=0.95) over an already-sorted list."""
    if not sorted_values:
        return 0.0
    rank = max(0, min(len(sorted_values) - 1, round(pct * len(sorted_values)) - 1))
    return sorted_values[rank]


def _report(latencies: list[float], total_cost: float, total: int, wall: float) -> None:
    ms = sorted(x * 1000 for x in latencies)
    cost_per_1000 = (total_cost / total) * 1000 if total else 0.0
    # Cost per turn is ~constant (same prompt shape, similar token counts), so cost-per-1000 scales
    # linearly from the sample — no need to fire a literal 1000 calls to know what 1000 would cost.
    basis = "measured" if total >= 1000 else f"extrapolated from {total}"
    print(f"\nPerformance — {total} requests")
    print(f"{'─' * 50}")
    print(f"  throughput     {total / wall:7.1f} req/s   ({wall:.1f}s wall)")
    print(f"  latency  p50   {median(ms):7.0f} ms")
    print(f"  latency  p95   {_percentile(ms, 0.95):7.0f} ms")
    print(f"  latency  p99   {_percentile(ms, 0.99):7.0f} ms")
    print(f"  LLM cost       ${total_cost:.4f} total   (${total_cost / total:.6f}/req)")
    print(f"  cost / 1000    ${cost_per_1000:.2f}   ({basis})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load-test the PAYBACK Assistant.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("-n", "--total", type=int, default=30, help="total requests (default 30)")
    parser.add_argument("-c", "--concurrency", type=int, default=5, help="in-flight (default 5)")
    args = parser.parse_args()

    print(
        f"PAYBACK Assistant — load test: {args.total} requests, "
        f"{args.concurrency} concurrent, against {args.base_url}"
    )
    try:
        start = time.perf_counter()
        latencies, total_cost = asyncio.run(_run(args.base_url, args.total, args.concurrency))
        _report(latencies, total_cost, args.total, time.perf_counter() - start)
    except httpx.HTTPError as exc:
        sys.exit(f"\nLoad test failed talking to {args.base_url}: {exc}\nIs the stack up? (make up)")


if __name__ == "__main__":
    main()
