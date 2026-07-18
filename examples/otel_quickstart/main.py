#!/usr/bin/env python3
"""Helios OTel quickstart: emit a small nested trace via the official
OpenTelemetry SDK and OTLP/HTTP protobuf exporter to Helios v2 ingestion.

Deterministic and offline-friendly: no LLM API key required; the "model"
span carries representative gen_ai.* attributes without calling a provider.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode


def build_provider(api_url: str, api_key: str, service_name: str) -> TracerProvider:
    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment.name": "development",
        }
    )
    # The project is derived from the API key; no project slug is sent.
    exporter = OTLPSpanExporter(
        endpoint=f"{api_url.rstrip('/')}/v1/otlp/traces",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def run_demo_trace(tracer: trace.Tracer) -> str:
    with tracer.start_as_current_span("agent.answer_question", kind=SpanKind.SERVER) as root:
        root.set_attribute("agent.input", "How do I rotate API keys without downtime?")

        with tracer.start_as_current_span("retriever.search", kind=SpanKind.CLIENT) as retrieval:
            retrieval.set_attribute("retrieval.query", "api key rotation policy")
            retrieval.set_attribute("retrieval.top_k", 3)
            retrieval.set_attribute(
                "retrieval.chunk_ids", ["docs/security.md", "docs/billing.md"]
            )
            time.sleep(0.01)

        with tracer.start_as_current_span("llm.generate", kind=SpanKind.CLIENT) as llm:
            llm.set_attribute("gen_ai.system", "openai")
            llm.set_attribute("gen_ai.request.model", "gpt-4o-mini")
            llm.set_attribute("gen_ai.usage.input_tokens", 1120)
            llm.set_attribute("gen_ai.usage.output_tokens", 240)
            llm.add_event(
                "gen_ai.content.completion",
                {"preview": "Create a new key, migrate clients, then revoke the old key."},
            )
            time.sleep(0.02)

        with tracer.start_as_current_span("tool.lookup_policy") as tool:
            tool.set_attribute("tool.name", "policy-engine")
            tool.set_attribute("tool.result", "policy/support-automation@v2")
            tool.set_status(Status(StatusCode.OK))
            time.sleep(0.005)

        root.set_status(Status(StatusCode.OK))
        trace_id = format(root.get_span_context().trace_id, "032x")
    return trace_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a demo OTel trace to Helios")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--service-name", default="otel-quickstart-agent")
    args = parser.parse_args()

    api_key = os.environ.get("HELIOS_API_KEY")
    if not api_key:
        print(
            "error: HELIOS_API_KEY is not set. Create a key with the admin CLI:\n"
            "  python -m app.cli.api_keys create --project-slug otel-quickstart \\\n"
            "      --name 'Local dev' --scopes traces:ingest,traces:read\n"
            "then: export HELIOS_API_KEY=<the key printed once>",
            file=sys.stderr,
        )
        return 1

    provider = build_provider(args.api_url, api_key, args.service_name)
    tracer = provider.get_tracer("helios.otel_quickstart")

    trace_id = run_demo_trace(tracer)

    # Flush and shut down cleanly so the batch is exported before exit.
    provider.force_flush()
    provider.shutdown()

    # The API key is never printed.
    print("OTel quickstart trace submitted")
    print(f"  trace_id:  {trace_id}")
    print("  read with your key, e.g.:")
    print(
        f'    curl -H "Authorization: Bearer $HELIOS_API_KEY" '
        f'"{args.api_url}/v2/traces"'
    )
    print(
        f'    curl -H "Authorization: Bearer $HELIOS_API_KEY" '
        f'"{args.api_url}/v2/traces/{trace_id}"'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
