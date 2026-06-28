"""Run the assistant demo: five queries across languages and intents → JSON.

A thin HTTP *client* of the running service — exactly how a real caller (or a reviewer) uses the
assistant. It loads the queries from ``queries.json``, sends each to ``POST /assist``, and prints
the structured response. When a query is vague the agent replies with a clarifying question; the
client then answers it via ``POST /assist/resume`` to show the multi-turn flow end to end.

``make demo`` runs it inside the api container against the local service; point ``--base-url`` at
a deployed URL to demo that instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

QUERIES_PATH = Path(__file__).parent / "queries.json"


class AssistClient:
    """Minimal client for the assistant's two endpoints."""

    def __init__(self, base_url: str) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=60)

    def assist(self, query: str) -> dict:
        return self._http.post("/assist", json={"query": query}).raise_for_status().json()

    def resume(self, thread_id: str, answer: str) -> dict:
        body = {"thread_id": thread_id, "answer": answer}
        return self._http.post("/assist/resume", json=body).raise_for_status().json()

    def close(self) -> None:
        self._http.close()


def load_queries() -> list[dict]:
    """Load the demo queries (data lives in queries.json, not in code)."""
    return json.loads(QUERIES_PATH.read_text())["queries"]


def _print(title: str, payload: dict) -> None:
    print(f"\n{'─' * 78}\n▶ {title}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def run(client: AssistClient, queries: list[dict]) -> None:
    for case in queries:
        result = client.assist(case["query"])
        _print(f"{case['label']}  —  {case['query']!r}", result)

        # A vague query pauses to clarify; answer it to demonstrate the resume flow.
        if result.get("type") == "clarify":
            answer = case.get("clarify_answer", "")
            resumed = client.resume(result["thread_id"], answer)
            _print(f"   ↳ resume with {answer!r}", resumed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PAYBACK Assistant demo.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    queries = load_queries()
    print(f"PAYBACK Assistant — demo ({len(queries)} queries) against {args.base_url}")

    client = AssistClient(args.base_url)
    try:
        run(client, queries)
    except httpx.HTTPError as exc:
        sys.exit(f"\nDemo failed talking to {args.base_url}: {exc}\nIs the stack running? (make up)")
    finally:
        client.close()


if __name__ == "__main__":
    main()
