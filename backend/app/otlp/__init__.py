"""OTLP/HTTP protobuf handling for the canonical v2 ingestion path."""

from app.otlp.parser import (
    OtlpDecodeError,
    OtlpValidationError,
    NormalizedSpan,
    parse_export_request,
)

__all__ = [
    "OtlpDecodeError",
    "OtlpValidationError",
    "NormalizedSpan",
    "parse_export_request",
]
