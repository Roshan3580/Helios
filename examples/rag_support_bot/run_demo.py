#!/usr/bin/env python3
"""Deterministic RAG support bot demo that submits a trace to Helios."""

from __future__ import annotations

import argparse
import sys
import time

from helios_sdk import HeliosClient, HeliosConnectionError, HeliosAPIError

from knowledge_base import keyword_search, rerank_chunks

DEFAULT_QUERIES = (
    "How do I rotate API keys without downtime?",
    "Can I export traces to Datadog?",
    "Why did my RAG answer miss a citation?",
)


def simulate_llm_answer(query: str, chunks: list[str]) -> tuple[str, int, float, str]:
    if "datadog" in query.lower():
        return (
            "Configure the Helios export webhook and map span fields to Datadog intake.",
            980,
            0.0031,
            "warning",
        )
    if "citation" in query.lower():
        return (
            "Check retriever recall and reranker uplift; low citation coverage often means missed chunks.",
            1120,
            0.0038,
            "warning",
        )
    return (
        "Create a new API key, update clients, validate traffic, then revoke the old key.",
        1240,
        0.0042,
        "success",
    )


def run_pipeline(client: HeliosClient, query: str) -> str:
    trace = client.create_trace(
        user_query=query,
        app_name="rag-support-bot",
        model="gpt-4o-mini",
    )

    with trace.span("user.query", span_type="input") as span:
        span.set_input(query)
        span.set_metadata({"channel": "cli", "sdk": "helios_sdk"})

    time.sleep(0.02)
    candidates = keyword_search(query, top_k=3)
    with trace.span("retriever.keyword_search", span_type="rag", provider="local-index") as span:
        span.set_input(query)
        span.set_output(f"Retrieved {len(candidates)} candidate chunks")
        span.set_metadata(
            {
                "top_k": 3,
                "chunks": [chunk.doc_id for chunk, _ in candidates],
                "scores": [score for _, score in candidates],
            }
        )

    time.sleep(0.015)
    reranked = rerank_chunks(query, candidates)
    with trace.span("reranker.score_chunks", span_type="rag", provider="heuristic-reranker") as span:
        span.set_input(query)
        span.set_output(f"Reranked {len(reranked)} chunks")
        span.set_metadata(
            {
                "chunks": [chunk.doc_id for chunk, _ in reranked],
                "scores": [score for _, score in reranked],
            }
        )

    answer, tokens, cost, llm_status = simulate_llm_answer(query, [chunk.doc_id for chunk, _ in reranked])
    time.sleep(0.03)
    with trace.span(
        "llm.generate_answer",
        span_type="llm",
        provider="simulated-openai",
        model="gpt-4o-mini",
        status=llm_status,
    ) as span:
        span.set_input(f"Question: {query}\nContext: {[chunk.doc_id for chunk, _ in reranked]}")
        span.set_output(answer)
        span.set_tokens(tokens)
        span.set_cost(cost)
        span.set_metadata({"citation_count": min(2, len(reranked))})

    policy_status = "success" if "rotate" in query.lower() else "success"
    with trace.span("tool.lookup_policy", span_type="tool", provider="policy-engine") as span:
        span.set_input("lookup_support_policy")
        span.set_output("policy/support-automation@v2")
        span.set_metadata({"policy_id": "support-automation@v2"})
        span.set_status(policy_status)

    with trace.span("response.finalize", span_type="output") as span:
        span.set_input(answer)
        span.set_output(answer)
        span.set_metadata({"format": "markdown", "citations": min(2, len(reranked))})

    if llm_status == "warning":
        trace.status = "warning"

    result = client.submit_trace(trace)
    return result["trace_id"], trace.span_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a deterministic RAG support trace to Helios")
    parser.add_argument("--query", default=DEFAULT_QUERIES[0], help="User query to simulate")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Helios backend base URL")
    parser.add_argument(
        "--frontend-url",
        default="http://localhost:5173",
        help="Helios frontend base URL for viewing traces",
    )
    args = parser.parse_args()

    client = HeliosClient(
        base_url=args.api_url,
        project_slug="rag-support-bot",
        project_name="RAG Support Bot",
        environment="development",
    )

    print("Helios RAG Support Bot demo")
    print(f"  backend:  {args.api_url}")
    print(f"  query:    {args.query}")
    print()

    try:
        trace_id, span_count = run_pipeline(client, args.query)
    except HeliosConnectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except HeliosAPIError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Trace submitted successfully")
    print(f"  trace_id:   {trace_id}")
    print(f"  spans:      {span_count}")
    print(f"  backend:    {args.api_url}")
    print(f"  view trace: {args.frontend_url.rstrip('/')}/app/traces/{trace_id}")
    print()
    print("Tip: set VITE_HELIOS_DEMO_MODE=false and open the link above to view live data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
