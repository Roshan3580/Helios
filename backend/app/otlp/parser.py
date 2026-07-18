"""Decode and normalize OTLP ExportTraceServiceRequest protobuf payloads.

Persistence code never touches protobuf objects: this module converts the
official generated classes into plain typed NormalizedSpan structures.

Batch failure behavior: any individual invalid span (bad trace/span ID
length, all-zero IDs) rejects the entire request via OtlpValidationError.
Partial acceptance is intentionally not implemented; the endpoint fails the
whole export transactionally rather than claiming partial success.

Nothing GenAI-specific is inferred here: attributes are preserved exactly as
sent, and no user-query/model/token/cost values are invented.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_TRACE_ID_LEN_BYTES = 16
_SPAN_ID_LEN_BYTES = 8

# Standard resource attribute keys (semantic conventions).
_SERVICE_NAME_KEY = "service.name"
_ENVIRONMENT_KEYS = ("deployment.environment.name", "deployment.environment")
_DEFAULT_SERVICE_NAME = "unknown_service"


class OtlpDecodeError(Exception):
    """Raised when the request body is not a valid ExportTraceServiceRequest."""


class OtlpValidationError(Exception):
    """Raised when a decoded span violates OTLP identity/format rules."""


@dataclass(frozen=True)
class NormalizedSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    kind: int
    start_time: datetime
    end_time: datetime
    duration_ns: int
    status_code: int
    status_message: str | None
    trace_state: str | None
    trace_flags: int
    resource_attributes: dict[str, Any]
    scope_name: str | None
    scope_version: str | None
    scope_attributes: dict[str, Any]
    attributes: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    dropped_attributes_count: int = 0
    dropped_events_count: int = 0
    dropped_links_count: int = 0
    service_name: str = _DEFAULT_SERVICE_NAME
    environment: str | None = None


def ns_to_datetime(epoch_nanos: int) -> datetime:
    """Unix epoch nanoseconds -> tz-aware UTC datetime.

    Python datetimes carry microsecond precision; sub-microsecond detail is
    truncated here, while exact durations are preserved via duration_ns.
    """
    seconds, rem_nanos = divmod(int(epoch_nanos), 1_000_000_000)
    return _EPOCH + timedelta(seconds=seconds, microseconds=rem_nanos // 1_000)


def decode_trace_id(raw: bytes) -> str:
    if len(raw) != _TRACE_ID_LEN_BYTES or raw == b"\x00" * _TRACE_ID_LEN_BYTES:
        raise OtlpValidationError(
            f"invalid trace_id: expected {_TRACE_ID_LEN_BYTES} non-zero bytes, "
            f"got {len(raw)} bytes"
        )
    return raw.hex()


def decode_span_id(raw: bytes) -> str:
    if len(raw) != _SPAN_ID_LEN_BYTES or raw == b"\x00" * _SPAN_ID_LEN_BYTES:
        raise OtlpValidationError(
            f"invalid span_id: expected {_SPAN_ID_LEN_BYTES} non-zero bytes, "
            f"got {len(raw)} bytes"
        )
    return raw.hex()


def decode_parent_span_id(raw: bytes) -> str | None:
    if not raw:
        return None
    return decode_span_id(raw)


def any_value_to_python(value) -> Any:
    """Recursively convert an OTel AnyValue to plain JSON-safe Python."""
    which = value.WhichOneof("value")
    if which is None:
        return None
    if which == "string_value":
        return value.string_value
    if which == "bool_value":
        return value.bool_value
    if which == "int_value":
        return value.int_value
    if which == "double_value":
        return value.double_value
    if which == "bytes_value":
        # JSONB cannot hold raw bytes; base64 keeps the value round-trippable.
        return {"__bytes_b64__": base64.b64encode(value.bytes_value).decode("ascii")}
    if which == "array_value":
        return [any_value_to_python(item) for item in value.array_value.values]
    if which == "kvlist_value":
        return key_values_to_dict(value.kvlist_value.values)
    return None  # future AnyValue kinds degrade to null rather than crash


def key_values_to_dict(key_values) -> dict[str, Any]:
    return {kv.key: any_value_to_python(kv.value) for kv in key_values}


def _events_to_python(events) -> list[dict[str, Any]]:
    return [
        {
            "name": event.name,
            "timestamp": ns_to_datetime(event.time_unix_nano).isoformat(),
            "attributes": key_values_to_dict(event.attributes),
            "dropped_attributes_count": event.dropped_attributes_count,
        }
        for event in events
    ]


def _links_to_python(links) -> list[dict[str, Any]]:
    return [
        {
            "trace_id": decode_trace_id(link.trace_id),
            "span_id": decode_span_id(link.span_id),
            "trace_state": link.trace_state or None,
            "attributes": key_values_to_dict(link.attributes),
            "dropped_attributes_count": link.dropped_attributes_count,
            "flags": link.flags,
        }
        for link in links
    ]


def parse_export_request(payload: bytes) -> list[NormalizedSpan]:
    """Decode + normalize an OTLP export. Raises on malformed/invalid input."""
    request = ExportTraceServiceRequest()
    try:
        request.ParseFromString(payload)
    except DecodeError as exc:
        raise OtlpDecodeError("request body is not a valid OTLP ExportTraceServiceRequest") from exc

    normalized: list[NormalizedSpan] = []
    for resource_spans in request.resource_spans:
        resource_attributes = key_values_to_dict(resource_spans.resource.attributes)

        service_name_value = resource_attributes.get(_SERVICE_NAME_KEY)
        service_name = (
            service_name_value
            if isinstance(service_name_value, str) and service_name_value
            else _DEFAULT_SERVICE_NAME
        )

        environment: str | None = None
        for key in _ENVIRONMENT_KEYS:
            env_value = resource_attributes.get(key)
            if isinstance(env_value, str) and env_value:
                environment = env_value
                break

        for scope_spans in resource_spans.scope_spans:
            scope = scope_spans.scope
            scope_name = scope.name or None
            scope_version = scope.version or None
            scope_attributes = key_values_to_dict(scope.attributes)

            for span in scope_spans.spans:
                start_time = ns_to_datetime(span.start_time_unix_nano)
                end_time = ns_to_datetime(span.end_time_unix_nano)
                duration_ns = max(
                    0, int(span.end_time_unix_nano) - int(span.start_time_unix_nano)
                )
                normalized.append(
                    NormalizedSpan(
                        trace_id=decode_trace_id(span.trace_id),
                        span_id=decode_span_id(span.span_id),
                        parent_span_id=decode_parent_span_id(span.parent_span_id),
                        name=span.name,
                        kind=int(span.kind),
                        start_time=start_time,
                        end_time=end_time,
                        duration_ns=duration_ns,
                        status_code=int(span.status.code),
                        status_message=span.status.message or None,
                        trace_state=span.trace_state or None,
                        trace_flags=int(span.flags),
                        resource_attributes=resource_attributes,
                        scope_name=scope_name,
                        scope_version=scope_version,
                        scope_attributes=scope_attributes,
                        attributes=key_values_to_dict(span.attributes),
                        events=_events_to_python(span.events),
                        links=_links_to_python(span.links),
                        dropped_attributes_count=span.dropped_attributes_count,
                        dropped_events_count=span.dropped_events_count,
                        dropped_links_count=span.dropped_links_count,
                        service_name=service_name,
                        environment=environment,
                    )
                )
    return normalized
