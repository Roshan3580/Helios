#!/usr/bin/env python3
"""Post a deterministic OTLP protobuf export using a project API key."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from otlp_helpers import (  # noqa: E402
    PROTOBUF_HEADERS,
    SPAN_ID_CHILD,
    SPAN_ID_GRANDCHILD,
    SPAN_ID_ROOT,
    any_int,
    any_string,
    kv,
    make_request,
    make_span,
)
from opentelemetry.proto.trace.v1.trace_pb2 import Span, Status  # noqa: E402
import httpx  # noqa: E402


def build_payload(trace_hex: str, *, now_ns: int) -> bytes:
    trace_id = bytes.fromhex(trace_hex)
    root = make_span(
        trace_id=trace_id,
        span_id=SPAN_ID_ROOT,
        name="agent.run",
        start_offset_ns=0,
        duration_ns=50_000_000,
        attributes=[kv("helios.span_type", any_string("agent"))],
    )
    # Override absolute times relative to now for dashboard windows.
    root.start_time_unix_nano = now_ns
    root.end_time_unix_nano = now_ns + 50_000_000

    model = make_span(
        trace_id=trace_id,
        span_id=SPAN_ID_CHILD,
        parent_span_id=SPAN_ID_ROOT,
        name="chat.completions",
        start_offset_ns=1_000_000,
        duration_ns=20_000_000,
        attributes=[
            kv("gen_ai.request.model", any_string("gpt-4o-mini")),
            kv("gen_ai.usage.input_tokens", any_int(120)),
            kv("gen_ai.usage.output_tokens", any_int(40)),
            kv("helios.span_type", any_string("llm")),
        ],
    )
    model.start_time_unix_nano = now_ns + 1_000_000
    model.end_time_unix_nano = now_ns + 21_000_000

    tool = make_span(
        trace_id=trace_id,
        span_id=SPAN_ID_GRANDCHILD,
        parent_span_id=SPAN_ID_CHILD,
        name="tool.lookup",
        start_offset_ns=5_000_000,
        duration_ns=10_000_000,
        status_code=Status.STATUS_CODE_ERROR,
        status_message="lookup failed",
        attributes=[kv("helios.span_type", any_string("tool"))],
    )
    tool.start_time_unix_nano = now_ns + 5_000_000
    tool.end_time_unix_nano = now_ns + 15_000_000
    # silence unused Span import warning path
    _ = Span.SPAN_KIND_INTERNAL

    req = make_request([root, model, tool], service_name="e2e-agent")
    return req.SerializeToString()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--trace-id", required=True, help="32 lowercase hex chars")
    args = parser.parse_args()
    token = args.api_key_file.read_text(encoding="utf-8").strip()
    if not token.startswith("hel_proj_"):
        print("invalid key file", file=sys.stderr)
        return 2
    now_ns = time.time_ns()
    body = build_payload(args.trace_id, now_ns=now_ns)
    url = args.api_url.rstrip("/") + "/v1/otlp/traces"
    response = httpx.post(
        url,
        content=body,
        headers={**PROTOBUF_HEADERS, "Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    print(f"status={response.status_code}")
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
