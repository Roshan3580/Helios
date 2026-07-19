"""Safe attribute reading and redaction for analyst evidence.

Telemetry is treated as untrusted data. Only verified attribute keys needed by
current rules are read for classification. Supporting attributes copied into
findings are allowlisted, size-bounded, and never include content or secrets.
"""

from __future__ import annotations

from typing import Any

from app.analyst.thresholds import MAX_ATTR_STRING_LEN
from app.otel_genai_attributes import (
    INPUT_TOKEN_KEYS,
    OUTPUT_TOKEN_KEYS,
    REQUEST_MODEL_KEY,
    RESPONSE_MODEL_KEY,
)

# Verified classification / evidence keys (SDK + dashboard contract).
HELIOS_SPAN_TYPE = "helios.span.type"
TOOL_NAME = "tool.name"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"

ALLOWED_SUPPORTING_KEYS = frozenset(
    {
        HELIOS_SPAN_TYPE,
        TOOL_NAME,
        GEN_AI_OPERATION_NAME,
        REQUEST_MODEL_KEY,
        RESPONSE_MODEL_KEY,
        INPUT_TOKEN_KEYS[0],
        OUTPUT_TOKEN_KEYS[0],
        "name",
        "status_code",
        "status_message",
        "kind",
        "scope_name",
    }
)

# Substrings that mark secret-like attribute keys (case-insensitive).
# Note: allowlisted GenAI usage keys contain "token" and are exempted in
# is_secret_like_key so telemetry counters are not treated as secrets.
_SECRET_KEY_FRAGMENTS = (
    "authorization",
    "api_key",
    "api-key",
    "apikey",
    "password",
    "passwd",
    "secret",
    "token",
    "cookie",
    "session",
    "credential",
)

# Content-bearing keys / fragments never copied into findings.
_CONTENT_KEY_FRAGMENTS = (
    "prompt",
    "completion",
    "message",
    "content",
    "document",
    "argument",
    "arguments",
    "input_messages",
    "output_messages",
    "gen_ai.content",
    "retrieval.query",
    "retrieval.document",
    "tool.result",
    "tool.arguments",
    "agent.input",
)


def _as_mapping(attributes: Any) -> dict[str, Any]:
    if not isinstance(attributes, dict):
        return {}
    return attributes


def is_secret_like_key(key: str) -> bool:
    if key in ALLOWED_SUPPORTING_KEYS:
        return False
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SECRET_KEY_FRAGMENTS)


def is_content_like_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _CONTENT_KEY_FRAGMENTS)


def bound_string(value: Any, *, max_len: int = MAX_ATTR_STRING_LEN) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value):  # NaN
            return None
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        # Objects/lists are not copied into factual attribute evidence.
        return None
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def read_string_attr(attributes: Any, key: str) -> str | None:
    attrs = _as_mapping(attributes)
    if key not in attrs:
        return None
    raw = attrs[key]
    if isinstance(raw, str):
        text = raw.strip()
        return text or None
    if isinstance(raw, (int, float, bool)):
        return bound_string(raw)
    return None


def read_number_attr(attributes: Any, key: str) -> float | None:
    """Return a finite number from JSON, or None. Never estimates."""
    attrs = _as_mapping(attributes)
    if key not in attrs:
        return None
    raw = attrs[key]
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return float(raw)
    if isinstance(raw, float):
        if raw != raw or raw in (float("inf"), float("-inf")):
            return None
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    return None


def read_token_total(attributes: Any, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        number = read_number_attr(attributes, key)
        if number is not None:
            return int(number)
    return None


def resolve_model(attributes: Any) -> str | None:
    return read_string_attr(attributes, REQUEST_MODEL_KEY) or read_string_attr(
        attributes, RESPONSE_MODEL_KEY
    )


def span_type(attributes: Any) -> str | None:
    return read_string_attr(attributes, HELIOS_SPAN_TYPE)


def is_tool_like(attributes: Any) -> bool:
    if span_type(attributes) == "tool":
        return True
    tool = read_string_attr(attributes, TOOL_NAME)
    return bool(tool)


def is_model_like(attributes: Any) -> bool:
    if span_type(attributes) == "llm":
        return True
    if resolve_model(attributes):
        return True
    if read_string_attr(attributes, GEN_AI_OPERATION_NAME):
        return True
    return False


def has_model_data(attributes: Any) -> bool:
    return resolve_model(attributes) is not None


def has_token_data(attributes: Any) -> bool:
    return (
        read_token_total(attributes, INPUT_TOKEN_KEYS) is not None
        or read_token_total(attributes, OUTPUT_TOKEN_KEYS) is not None
    )


def tool_identity(attributes: Any, *, span_name: str) -> str:
    """Normalized identity for grouping repeated tool calls."""
    explicit = read_string_attr(attributes, TOOL_NAME)
    if explicit:
        return explicit.lower()
    return (span_name or "").strip().lower() or "unnamed-tool"


def model_group_key(attributes: Any, *, span_name: str) -> tuple[str, str]:
    model = (resolve_model(attributes) or "").lower()
    operation = (
        read_string_attr(attributes, GEN_AI_OPERATION_NAME)
        or (span_name or "").strip()
        or "unnamed-operation"
    )
    return model, operation.lower()


def sanitize_supporting_attributes(
    attributes: Any,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a small allowlisted map safe to attach to a finding."""
    attrs = _as_mapping(attributes)
    out: dict[str, Any] = {}
    for key in sorted(ALLOWED_SUPPORTING_KEYS):
        if key in ("name", "status_code", "kind", "scope_name"):
            continue
        if key not in attrs:
            continue
        if is_secret_like_key(key) or is_content_like_key(key):
            continue
        if key in INPUT_TOKEN_KEYS or key in OUTPUT_TOKEN_KEYS:
            number = read_number_attr(attrs, key)
            if number is not None:
                out[key] = int(number)
            continue
        text = bound_string(attrs[key])
        if text is not None:
            out[key] = text
    if extra:
        for key, value in extra.items():
            if key not in ALLOWED_SUPPORTING_KEYS:
                continue
            if is_secret_like_key(key) or is_content_like_key(key):
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out[key] = value
            else:
                text = bound_string(value)
                if text is not None:
                    out[key] = text
    # Hard cap count.
    if len(out) > 12:
        keys = sorted(out.keys())[:12]
        out = {k: out[k] for k in keys}
    return out
