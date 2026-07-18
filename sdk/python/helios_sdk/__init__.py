"""Helios Python SDK.

Two APIs share one distribution:

- Legacy ``HeliosClient`` / ``TraceBuilder`` / ``SpanRecorder`` submit to the
  ``/v1/traces`` JSON endpoint (dependency-light; always importable).
- ``Helios`` is the v2 OpenTelemetry runtime that exports standard OTLP/HTTP
  protobuf spans to ``/v1/otlp/traces``. It requires the ``[otel]`` extra and is
  imported lazily, so ``import helios_sdk`` never pulls in OpenTelemetry.
"""

from helios_sdk.client import HeliosClient, SpanRecorder, TraceBuilder
from helios_sdk.errors import (
    HeliosAPIError,
    HeliosConfigurationError,
    HeliosConnectionError,
    HeliosError,
    HeliosInstrumentationError,
)

__all__ = [
    "HeliosClient",
    "TraceBuilder",
    "SpanRecorder",
    "HeliosError",
    "HeliosConnectionError",
    "HeliosAPIError",
    "HeliosConfigurationError",
    "HeliosInstrumentationError",
    "Helios",
]

__version__ = "0.2.0"


def __getattr__(name: str):
    # Lazy import so the v2 runtime's OpenTelemetry dependency is only required
    # when Helios is actually used, not on `import helios_sdk`.
    if name == "Helios":
        try:
            from helios_sdk.runtime import Helios
        except ImportError as exc:  # pragma: no cover - exercised via extras
            raise ImportError(
                "helios_sdk.Helios requires the OpenTelemetry runtime. Install with:\n"
                '    pip install "helios-sdk[otel]"  (add ",openai" for OpenAI)'
            ) from exc
        return Helios
    raise AttributeError(f"module 'helios_sdk' has no attribute {name!r}")
