#!/usr/bin/env python3
"""Smoke-test an installed Helios Python SDK artifact without network calls."""

from __future__ import annotations

import argparse
from importlib.metadata import version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shape", choices=("base", "otel", "openai", "combined"), required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    import helios_sdk
    from helios_sdk import HeliosClient, SpanRecorder, TraceBuilder

    assert HeliosClient is not None
    assert TraceBuilder is not None
    assert SpanRecorder is not None
    assert helios_sdk.__version__ == args.version
    assert version("helios-observatory-sdk") == args.version

    if args.shape != "base":
        from helios_sdk import Helios
        from opentelemetry.sdk.trace import TracerProvider

        assert Helios is not None
        assert TracerProvider is not None

    if args.shape in {"openai", "combined"}:
        from openai import OpenAI
        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

        assert OpenAI is not None
        assert OpenAIInstrumentor is not None

    print(f"Installed artifact smoke test passed: {args.shape}, version {args.version}")


if __name__ == "__main__":
    main()
