"""Helios v2 OTLP runtime: standard OpenTelemetry spans exported to Helios.

Public entry point is ``Helios.configure(...)``. This module imports the
OpenTelemetry API/SDK/exporter (the ``otel`` extra) but never OpenAI — the
OpenAI instrumentor is imported lazily inside ``instrument_openai``.

Importing this module does not touch the global tracer provider or perform any
network activity; only ``configure()`` does.
"""

from __future__ import annotations

import atexit
import functools
import inspect
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import ProxyTracerProvider, SpanKind, Status, StatusCode

from helios_sdk import semconv
from helios_sdk.config import HeliosConfig, resolve_config
from helios_sdk.errors import HeliosConfigurationError, HeliosInstrumentationError

# Upstream GenAI content-capture control (adapted in one place). The maintained
# instrumentor/util-genai takes an enum: NO_CONTENT | SPAN_ONLY | EVENT_ONLY |
# SPAN_AND_EVENT. Helios exports traces (not logs), so opt-in uses SPAN_ONLY so
# content lands in span attributes the OTLP trace exporter sends.
_GENAI_CAPTURE_ENV = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
_GENAI_CAPTURE_ON = "SPAN_ONLY"
_GENAI_CAPTURE_OFF = "NO_CONTENT"

_ALLOWED_SCALARS = (str, bool, int, float)

_LOCK = threading.RLock()
_active: "Helios | None" = None


def _normalize_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    """Coerce attribute values to OTel-safe types; drop None; stringify the rest."""
    if not attributes:
        return {}
    result: dict[str, Any] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, bool) or isinstance(value, (str, int, float)):
            result[key] = value
        elif isinstance(value, (list, tuple)) and value and all(
            isinstance(item, _ALLOWED_SCALARS) for item in value
        ):
            result[key] = list(value)
        else:
            result[key] = str(value)
    return result


class Helios:
    """Configured Helios telemetry runtime. Create via ``Helios.configure``."""

    def __init__(
        self,
        config: HeliosConfig,
        provider: SDKTracerProvider,
        processor: BatchSpanProcessor,
        *,
        owns_provider: bool,
    ) -> None:
        self._config = config
        self._provider = provider
        self._processor = processor
        self._owns_provider = owns_provider
        self._tracer = provider.get_tracer("helios_sdk")
        self._openai_instrumentor: Any = None
        self._is_shutdown = False
        self._lock = threading.RLock()

    # ---- construction -----------------------------------------------------

    @classmethod
    def configure(
        cls,
        *,
        api_key: str | None = None,
        service_name: str | None = None,
        endpoint: str | None = None,
        environment: str | None = None,
        capture_content: bool | None = None,
        timeout: float | None = None,
    ) -> "Helios":
        """Configure the Helios runtime. Idempotent for identical config.

        Provider ownership:
        - no real SDK provider yet -> Helios creates and installs one (owns it);
        - a compatible SDK provider already installed -> Helios attaches only its
          export processor (does not replace it);
        - an incompatible/foreign provider -> raises rather than replacing it.
        """
        config = resolve_config(
            api_key=api_key,
            service_name=service_name,
            endpoint=endpoint,
            environment=environment,
            capture_content=capture_content,
            timeout=timeout,
        )

        global _active
        with _LOCK:
            if _active is not None and not _active._is_shutdown:
                if _active._config == config:
                    return _active  # idempotent
                raise HeliosConfigurationError(
                    "Helios is already configured with different settings; "
                    "call shutdown() before reconfiguring."
                )

            exporter = OTLPSpanExporter(
                endpoint=config.traces_endpoint,
                headers=dict(config.headers),
                timeout=int(config.timeout),
            )
            processor = BatchSpanProcessor(exporter)

            current = trace.get_tracer_provider()
            if isinstance(current, SDKTracerProvider):
                # Attach to the existing provider without replacing it.
                current.add_span_processor(processor)
                helios = cls(config, current, processor, owns_provider=False)
            elif isinstance(current, ProxyTracerProvider):
                resource_attrs = {"service.name": config.service_name}
                if config.environment:
                    resource_attrs["deployment.environment.name"] = config.environment
                provider = SDKTracerProvider(resource=Resource.create(resource_attrs))
                provider.add_span_processor(processor)
                trace.set_tracer_provider(provider)
                helios = cls(config, provider, processor, owns_provider=True)
            else:
                raise HeliosConfigurationError(
                    "a non-OpenTelemetry-SDK tracer provider is already installed "
                    f"({type(current).__name__}); refusing to replace it."
                )

            _active = helios
            atexit.register(helios.shutdown)
            return helios

    # ---- lifecycle --------------------------------------------------------

    def force_flush(self, timeout_millis: int | None = None) -> bool:
        with self._lock:
            if self._is_shutdown:
                return False
            if timeout_millis is None:
                return self._processor.force_flush()
            return self._processor.force_flush(timeout_millis)

    def shutdown(self) -> None:
        """Flush and stop telemetry. Idempotent."""
        global _active
        with self._lock:
            if self._is_shutdown:
                return
            self._is_shutdown = True
            try:
                if self._owns_provider:
                    # Shuts down all processors (flush included).
                    self._provider.shutdown()
                else:
                    self._processor.shutdown()
            finally:
                with _LOCK:
                    if _active is self:
                        _active = None

    # ---- raw access -------------------------------------------------------

    @property
    def tracer(self) -> trace.Tracer:
        """The underlying OpenTelemetry tracer for advanced use."""
        return self._tracer

    @property
    def config(self) -> HeliosConfig:
        return self._config

    def __repr__(self) -> str:  # never expose the API key
        return (
            f"Helios(service_name={self._config.service_name!r}, "
            f"endpoint={self._config.endpoint!r}, owns_provider={self._owns_provider})"
        )

    # ---- manual semantic helpers -----------------------------------------

    @contextmanager
    def _span(
        self,
        name: str,
        span_type: str,
        attributes: dict[str, Any] | None,
        *,
        extra: dict[str, Any] | None = None,
    ) -> Iterator[trace.Span]:
        attrs = _normalize_attributes(attributes)
        attrs[semconv.HELIOS_SPAN_TYPE] = span_type
        if extra:
            attrs.update(_normalize_attributes(extra))
        kind = semconv.SPAN_KIND_BY_TYPE.get(span_type, SpanKind.INTERNAL)
        with self._tracer.start_as_current_span(
            name, kind=kind, attributes=attrs, record_exception=False
        ) as span:
            try:
                yield span
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise

    def agent(self, name: str, **attributes: Any):
        return self._span(name, semconv.SPAN_TYPE_AGENT, attributes)

    def retrieval(self, name: str, **attributes: Any):
        return self._span(name, semconv.SPAN_TYPE_RETRIEVAL, attributes)

    def tool(self, name: str, **attributes: Any):
        return self._span(name, semconv.SPAN_TYPE_TOOL, attributes)

    def llm(
        self,
        name: str,
        *,
        model: str | None = None,
        operation: str | None = None,
        system: str | None = None,
        **attributes: Any,
    ):
        # Map explicit values to GenAI conventions; never fabricate.
        extra: dict[str, Any] = {}
        if model is not None:
            extra[semconv.GEN_AI_REQUEST_MODEL] = model
        if operation is not None:
            extra[semconv.GEN_AI_OPERATION_NAME] = operation
        if system is not None:
            extra[semconv.GEN_AI_SYSTEM] = system
        return self._span(name, semconv.SPAN_TYPE_LLM, attributes, extra=extra)

    def span(self, name: str, **attributes: Any):
        return self._span(name, semconv.SPAN_TYPE_CUSTOM, attributes)

    def trace(self, name: str | None = None, **attributes: Any):
        """Decorator tracing a sync or async function as a custom span."""

        def decorator(func):
            span_name = name or func.__qualname__

            if inspect.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    with self._span(span_name, semconv.SPAN_TYPE_CUSTOM, attributes):
                        return await func(*args, **kwargs)

                return async_wrapper

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                with self._span(span_name, semconv.SPAN_TYPE_CUSTOM, attributes):
                    return func(*args, **kwargs)

            return sync_wrapper

        return decorator

    # ---- OpenAI auto-instrumentation -------------------------------------

    def instrument_openai(self, *, capture_content: bool | None = None) -> None:
        """Enable official OpenAI auto-instrumentation. Idempotent.

        Prompts/completions are NOT captured unless capture_content (or the
        HELIOS_CAPTURE_CONTENT config) is true.
        """
        try:
            from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
        except ImportError as exc:
            raise HeliosInstrumentationError(
                "OpenAI instrumentation requires the optional extra. Install with:\n"
                '    pip install "helios-sdk[otel,openai]"'
            ) from exc

        import os

        capture = self._config.capture_content if capture_content is None else bool(
            capture_content
        )
        # Single controlled place adapting Helios config to the upstream env var.
        os.environ[_GENAI_CAPTURE_ENV] = _GENAI_CAPTURE_ON if capture else _GENAI_CAPTURE_OFF

        with self._lock:
            if self._openai_instrumentor is not None:
                return  # already instrumented by this Helios
            instrumentor = OpenAIInstrumentor()
            if not instrumentor.is_instrumented_by_opentelemetry:
                instrumentor.instrument(tracer_provider=self._provider)
            self._openai_instrumentor = instrumentor

    def uninstrument_openai(self) -> None:
        with self._lock:
            if self._openai_instrumentor is not None:
                self._openai_instrumentor.uninstrument()
                self._openai_instrumentor = None


def _reset_for_tests() -> None:
    """Test-only: drop the active runtime and reset OTel global provider state.

    Not part of the public API. Used by isolation fixtures so global-provider
    behavior can be exercised deterministically without cross-test leakage.
    """
    global _active
    with _LOCK:
        if _active is not None:
            try:
                _active.shutdown()
            except Exception:
                pass
        _active = None
    # Reset the set-once global so a fresh provider can be installed.
    trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
