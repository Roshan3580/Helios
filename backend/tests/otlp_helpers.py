"""Builders for OTLP protobuf test requests using the official generated classes."""

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, InstrumentationScope, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span, Status

PROTOBUF_HEADERS = {"Content-Type": "application/x-protobuf"}

TRACE_ID_A = bytes.fromhex("0af7651916cd43dd8448eb211c80319c")
TRACE_ID_B = bytes.fromhex("1bf7651916cd43dd8448eb211c80319d")
SPAN_ID_ROOT = bytes.fromhex("b7ad6b7169203331")
SPAN_ID_CHILD = bytes.fromhex("c8be7c827a314442")
SPAN_ID_GRANDCHILD = bytes.fromhex("d9cf8d938b425553")

BASE_NS = 1_767_225_600_000_000_000  # 2026-01-01T00:00:00Z in Unix nanoseconds


def any_string(value: str) -> AnyValue:
    return AnyValue(string_value=value)


def kv(key: str, value: AnyValue) -> KeyValue:
    return KeyValue(key=key, value=value)


def make_span(
    *,
    trace_id: bytes = TRACE_ID_A,
    span_id: bytes = SPAN_ID_ROOT,
    parent_span_id: bytes = b"",
    name: str = "agent.run",
    kind: int = Span.SPAN_KIND_INTERNAL,
    start_offset_ns: int = 0,
    duration_ns: int = 5_000_000,  # 5 ms
    status_code: int = Status.STATUS_CODE_UNSET,
    status_message: str = "",
    attributes: list[KeyValue] | None = None,
    events: list[Span.Event] | None = None,
    links: list[Span.Link] | None = None,
    trace_state: str = "",
    flags: int = 0,
) -> Span:
    start = BASE_NS + start_offset_ns
    return Span(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        kind=kind,
        start_time_unix_nano=start,
        end_time_unix_nano=start + duration_ns,
        status=Status(code=status_code, message=status_message),
        attributes=attributes or [],
        events=events or [],
        links=links or [],
        trace_state=trace_state,
        flags=flags,
    )


def make_request(
    spans: list[Span],
    *,
    service_name: str = "test-service",
    resource_attributes: list[KeyValue] | None = None,
    scope_name: str = "helios.tests",
    scope_version: str = "0.0.1",
    scope_attributes: list[KeyValue] | None = None,
) -> ExportTraceServiceRequest:
    resource_attrs = [kv("service.name", any_string(service_name))]
    resource_attrs.extend(resource_attributes or [])
    return ExportTraceServiceRequest(
        resource_spans=[
            ResourceSpans(
                resource=Resource(attributes=resource_attrs),
                scope_spans=[
                    ScopeSpans(
                        scope=InstrumentationScope(
                            name=scope_name,
                            version=scope_version,
                            attributes=scope_attributes or [],
                        ),
                        spans=spans,
                    )
                ],
            )
        ]
    )


def nested_trace_spans(trace_id: bytes = TRACE_ID_A) -> list[Span]:
    """root -> child -> grandchild, with the grandchild in error status."""
    return [
        make_span(trace_id=trace_id, span_id=SPAN_ID_ROOT, name="agent.run",
                  kind=Span.SPAN_KIND_SERVER, start_offset_ns=0, duration_ns=50_000_000),
        make_span(trace_id=trace_id, span_id=SPAN_ID_CHILD, parent_span_id=SPAN_ID_ROOT,
                  name="retriever.search", kind=Span.SPAN_KIND_CLIENT,
                  start_offset_ns=1_000_000, duration_ns=10_000_000),
        make_span(trace_id=trace_id, span_id=SPAN_ID_GRANDCHILD, parent_span_id=SPAN_ID_CHILD,
                  name="tool.lookup", kind=Span.SPAN_KIND_INTERNAL,
                  start_offset_ns=12_000_000, duration_ns=3_000_000,
                  status_code=Status.STATUS_CODE_ERROR, status_message="tool timeout"),
    ]


def post_otlp(client, request: ExportTraceServiceRequest, *, project_slug: str = "otel-proj",
              extra_headers: dict | None = None):
    headers = {**PROTOBUF_HEADERS, "X-Helios-Project-Slug": project_slug}
    if extra_headers:
        headers.update(extra_headers)
    return client.post(
        "/v1/otlp/traces", content=request.SerializeToString(), headers=headers
    )
