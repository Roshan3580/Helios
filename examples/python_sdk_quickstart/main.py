#!/usr/bin/env python3
"""Helios v2 Python SDK quickstart.

Demonstrates the ``Helios`` OTLP runtime:
- ``Helios.configure`` with a project API key (from HELIOS_API_KEY)
- manual agent / retrieval / tool spans
- a deterministic OpenAI SDK call captured by auto-instrumentation

The OpenAI call uses a mock HTTP transport, so it exercises the real OpenAI
client and the official instrumentor with NO network access and NO paid request.
Prompt/response content is NOT captured unless HELIOS_CAPTURE_CONTENT=true.

The exported spans are real OTLP protobuf sent to /v1/otlp/traces; nothing about
the Helios payload is faked.
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

DETERMINISTIC_CHAT = {
    "id": "chatcmpl-quickstart",
    "object": "chat.completion",
    "created": 1,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Rotate keys with overlap, then revoke."},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 42, "completion_tokens": 12, "total_tokens": 54},
}


def _mock_openai_client():
    """A real openai.OpenAI client wired to a deterministic mock transport."""
    from openai import OpenAI

    return OpenAI(
        api_key="sk-quickstart-not-real",
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=DETERMINISTIC_CHAT))
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Helios v2 Python SDK quickstart")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--service-name", default="sdk-quickstart-agent")
    parser.add_argument("--query", default="How do I rotate API keys without downtime?")
    args = parser.parse_args()

    api_key = os.environ.get("HELIOS_API_KEY")
    if not api_key:
        print(
            "error: HELIOS_API_KEY is not set. Create a key with the admin CLI:\n"
            "  cd backend && python -m app.cli.api_keys create --project-slug sdk-quickstart \\\n"
            "      --name 'Local dev' --scopes traces:ingest,traces:read\n"
            "then: export HELIOS_API_KEY=<the key printed once>",
            file=sys.stderr,
        )
        return 1

    from helios_sdk import Helios

    helios = Helios.configure(
        api_key=api_key,
        service_name=args.service_name,
        endpoint=args.api_url,
        environment="development",
    )
    helios.instrument_openai()  # content capture stays OFF unless configured

    with helios.agent("support-agent") as agent_span:
        trace_id = format(agent_span.get_span_context().trace_id, "032x")

        with helios.retrieval("knowledge_base.search") as span:
            span.set_attribute("retrieval.top_k", 3)

        with helios.tool("lookup_policy") as span:
            span.set_attribute("tool.name", "policy-engine")

        # Auto-instrumented OpenAI call (deterministic, no network).
        _mock_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": args.query}],
        )

    helios.force_flush()
    helios.shutdown()

    # The API key is never printed.
    print("Helios SDK quickstart trace submitted")
    print(f"  trace_id:  {trace_id}")
    print(f"  service:   {args.service_name}")
    print("  read it (needs traces:read scope):")
    print(
        f'    curl -H "Authorization: Bearer $HELIOS_API_KEY" '
        f'"{args.api_url}/v2/traces/{trace_id}"'
    )

    # If the key also has traces:read, show the persisted trace summary.
    resp = httpx.get(
        f"{args.api_url.rstrip('/')}/v2/traces/{trace_id}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if resp.status_code == 200:
        detail = resp.json()
        span_names = [s["name"] for s in detail["spans"]]
        print(f"  persisted service: {detail['service_name']} · spans: {span_names}")
    elif resp.status_code == 403:
        print("  (this key is ingest-only; use a traces:read key to query)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
