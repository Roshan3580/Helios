"""Unit tests for OTLP protobuf decoding and normalization."""

from datetime import datetime, timezone

import pytest
from opentelemetry.proto.common.v1.common_pb2 import (
    AnyValue,
    ArrayValue,
    KeyValue,
    KeyValueList,
)
from opentelemetry.proto.trace.v1.trace_pb2 import Span, Status

from app.otlp.parser import (
    OtlpDecodeError,
    OtlpValidationError,
    any_value_to_python,
    decode_span_id,
    decode_trace_id,
    ns_to_datetime,
    parse_export_request,
)

from otlp_helpers import (
    BASE_NS,
    SPAN_ID_CHILD,
    SPAN_ID_ROOT,
    TRACE_ID_A,
    any_string,
    kv,
    make_request,
    make_span,
)


class TestIdConversion:
    def test_trace_id_converts_to_32_lowercase_hex(self):
        assert decode_trace_id(TRACE_ID_A) == "0af7651916cd43dd8448eb211c80319c"
        assert len(decode_trace_id(TRACE_ID_A)) == 32

    def test_span_id_converts_to_16_lowercase_hex(self):
        assert decode_span_id(SPAN_ID_ROOT) == "b7ad6b7169203331"
        assert len(decode_span_id(SPAN_ID_ROOT)) == 16

    def test_zero_trace_id_is_invalid(self):
        with pytest.raises(OtlpValidationError):
            decode_trace_id(b"\x00" * 16)

    def test_wrong_length_trace_id_is_invalid(self):
        with pytest.raises(OtlpValidationError):
            decode_trace_id(b"\x01" * 8)

    def test_zero_span_id_is_invalid(self):
        with pytest.raises(OtlpValidationError):
            decode_span_id(b"\x00" * 8)

    def test_wrong_length_span_id_is_invalid(self):
        with pytest.raises(OtlpValidationError):
            decode_span_id(b"\x01" * 4)


class TestTimestamps:
    def test_nanoseconds_convert_to_aware_utc(self):
        dt = ns_to_datetime(BASE_NS)
        assert dt == datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert dt.tzinfo is not None

    def test_sub_second_precision_preserved_to_microseconds(self):
        dt = ns_to_datetime(BASE_NS + 123_456_789)
        assert dt.microsecond == 123_456  # ns truncated to µs


class TestAnyValueConversion:
    def test_scalar_values(self):
        assert any_value_to_python(AnyValue(string_value="s")) == "s"
        assert any_value_to_python(AnyValue(bool_value=True)) is True
        assert any_value_to_python(AnyValue(int_value=42)) == 42
        assert any_value_to_python(AnyValue(double_value=1.5)) == 1.5
        assert any_value_to_python(AnyValue()) is None

    def test_bytes_value_base64_encoded(self):
        result = any_value_to_python(AnyValue(bytes_value=b"\x00\xff"))
        assert result == {"__bytes_b64__": "AP8="}

    def test_recursive_array_and_kvlist(self):
        value = AnyValue(
            array_value=ArrayValue(
                values=[
                    AnyValue(int_value=1),
                    AnyValue(
                        kvlist_value=KeyValueList(
                            values=[KeyValue(key="inner", value=AnyValue(string_value="x"))]
                        )
                    ),
                ]
            )
        )
        assert any_value_to_python(value) == [1, {"inner": "x"}]


class TestParseExportRequest:
    def test_valid_request_normalizes_all_fields(self):
        request = make_request(
            [
                make_span(
                    name="llm.generate",
                    kind=Span.SPAN_KIND_CLIENT,
                    parent_span_id=SPAN_ID_ROOT,
                    span_id=SPAN_ID_CHILD,
                    status_code=Status.STATUS_CODE_ERROR,
                    status_message="boom",
                    attributes=[kv("gen_ai.request.model", any_string("gpt-4o-mini"))],
                    trace_state="vendor=abc",
                    flags=1,
                )
            ],
            service_name="svc-a",
            resource_attributes=[kv("deployment.environment.name", any_string("staging"))],
            scope_name="my.scope",
            scope_version="1.2.3",
            scope_attributes=[kv("scope.key", any_string("v"))],
        )

        spans = parse_export_request(request.SerializeToString())

        assert len(spans) == 1
        span = spans[0]
        assert span.trace_id == TRACE_ID_A.hex()
        assert span.span_id == SPAN_ID_CHILD.hex()
        assert span.parent_span_id == SPAN_ID_ROOT.hex()
        assert span.name == "llm.generate"
        assert span.kind == Span.SPAN_KIND_CLIENT
        assert span.status_code == 2
        assert span.status_message == "boom"
        assert span.trace_state == "vendor=abc"
        assert span.trace_flags == 1
        assert span.service_name == "svc-a"
        assert span.environment == "staging"
        assert span.resource_attributes["service.name"] == "svc-a"
        assert span.scope_name == "my.scope"
        assert span.scope_version == "1.2.3"
        assert span.scope_attributes == {"scope.key": "v"}
        assert span.attributes == {"gen_ai.request.model": "gpt-4o-mini"}
        assert span.duration_ns == 5_000_000
        assert span.start_time.tzinfo is not None

    def test_events_preserved_with_attributes(self):
        event = Span.Event(
            name="tool.call",
            time_unix_nano=BASE_NS + 1_000_000,
            attributes=[kv("tool.name", any_string("lookup"))],
            dropped_attributes_count=2,
        )
        request = make_request([make_span(events=[event])])

        span = parse_export_request(request.SerializeToString())[0]

        assert span.events == [
            {
                "name": "tool.call",
                "timestamp": "2026-01-01T00:00:00.001000+00:00",
                "attributes": {"tool.name": "lookup"},
                "dropped_attributes_count": 2,
            }
        ]

    def test_links_preserved_with_attributes(self):
        link = Span.Link(
            trace_id=TRACE_ID_A,
            span_id=SPAN_ID_ROOT,
            trace_state="w3c=1",
            attributes=[kv("link.kind", any_string("followsFrom"))],
            dropped_attributes_count=1,
            flags=256,
        )
        request = make_request([make_span(links=[link])])

        span = parse_export_request(request.SerializeToString())[0]

        assert span.links == [
            {
                "trace_id": TRACE_ID_A.hex(),
                "span_id": SPAN_ID_ROOT.hex(),
                "trace_state": "w3c=1",
                "attributes": {"link.kind": "followsFrom"},
                "dropped_attributes_count": 1,
                "flags": 256,
            }
        ]

    def test_missing_service_name_defaults_without_inventing_values(self):
        request = make_request([make_span()])
        del request.resource_spans[0].resource.attributes[:]

        span = parse_export_request(request.SerializeToString())[0]

        assert span.service_name == "unknown_service"
        assert span.environment is None
        assert span.resource_attributes == {}

    def test_invalid_span_rejects_whole_batch(self):
        request = make_request(
            [make_span(), make_span(span_id=b"\x00" * 8)]  # second span invalid
        )
        with pytest.raises(OtlpValidationError):
            parse_export_request(request.SerializeToString())

    def test_malformed_protobuf_raises_decode_error(self):
        with pytest.raises(OtlpDecodeError):
            parse_export_request(b"\xff\xfe\xfd not protobuf")

    def test_dropped_counts_preserved(self):
        span_proto = make_span()
        span_proto.dropped_attributes_count = 3
        span_proto.dropped_events_count = 4
        span_proto.dropped_links_count = 5
        request = make_request([span_proto])

        span = parse_export_request(request.SerializeToString())[0]

        assert span.dropped_attributes_count == 3
        assert span.dropped_events_count == 4
        assert span.dropped_links_count == 5
