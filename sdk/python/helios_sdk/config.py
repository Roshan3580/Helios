"""Configuration for the Helios v2 OTLP runtime.

Resolves explicit arguments and environment variables into a validated,
immutable HeliosConfig. Contains no OpenTelemetry imports and performs no
network activity, so importing this module is cheap and side-effect free.

Precedence: explicit argument > Helios env var > recognized OTel env var >
default.

Environment variables:
    HELIOS_API_KEY          required (no default)
    HELIOS_ENDPOINT         base URL, default http://localhost:8000
    HELIOS_SERVICE_NAME     required unless OTEL_SERVICE_NAME is set
    HELIOS_ENVIRONMENT      optional deployment environment
    HELIOS_CAPTURE_CONTENT  optional bool, default false
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from helios_sdk.errors import HeliosConfigurationError

DEFAULT_ENDPOINT = "http://localhost:8000"
TRACES_PATH = "/v1/otlp/traces"
DEFAULT_TIMEOUT_SECONDS = 10.0

_TRUE_VALUES = {"true", "1", "yes", "on"}
_FALSE_VALUES = {"false", "0", "no", "off", ""}


def _parse_bool(value, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    raise HeliosConfigurationError(
        f"invalid boolean for {field_name}: {value!r} "
        "(use true/false)"
    )


def _first(*values):
    for value in values:
        if value is not None and value != "":
            return value
    return None


@dataclass(frozen=True)
class HeliosConfig:
    api_key: str
    service_name: str
    endpoint: str  # base URL, no path
    traces_endpoint: str  # full OTLP traces URL
    environment: str | None = None
    capture_content: bool = False
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    headers: dict = field(default_factory=dict)

    def __repr__(self) -> str:  # never expose the API key
        return (
            "HeliosConfig("
            f"service_name={self.service_name!r}, endpoint={self.endpoint!r}, "
            f"environment={self.environment!r}, capture_content={self.capture_content}, "
            f"timeout={self.timeout}, api_key='***')"
        )

    __str__ = __repr__


def _normalize_endpoint(base: str) -> tuple[str, str]:
    base = base.strip()
    if not (base.startswith("http://") or base.startswith("https://")):
        raise HeliosConfigurationError(
            f"endpoint must start with http:// or https:// (got {base!r})"
        )
    trimmed = base.rstrip("/")
    if trimmed.endswith(TRACES_PATH):
        traces = trimmed
        root = trimmed[: -len(TRACES_PATH)] or trimmed
    else:
        traces = f"{trimmed}{TRACES_PATH}"
        root = trimmed
    return root, traces


def resolve_config(
    *,
    api_key: str | None = None,
    service_name: str | None = None,
    endpoint: str | None = None,
    environment: str | None = None,
    capture_content: bool | None = None,
    timeout: float | None = None,
    env: dict | None = None,
) -> HeliosConfig:
    """Build a validated HeliosConfig from explicit args + environment."""
    env = os.environ if env is None else env

    resolved_key = _first(api_key, env.get("HELIOS_API_KEY"))
    if not resolved_key or not str(resolved_key).strip():
        raise HeliosConfigurationError(
            "api_key is required (pass api_key=... or set HELIOS_API_KEY)"
        )
    resolved_key = str(resolved_key).strip()

    resolved_service = _first(
        service_name, env.get("HELIOS_SERVICE_NAME"), env.get("OTEL_SERVICE_NAME")
    )
    if not resolved_service or not str(resolved_service).strip():
        raise HeliosConfigurationError(
            "service_name is required (pass service_name=... or set "
            "HELIOS_SERVICE_NAME / OTEL_SERVICE_NAME)"
        )
    resolved_service = str(resolved_service).strip()

    resolved_endpoint = _first(endpoint, env.get("HELIOS_ENDPOINT")) or DEFAULT_ENDPOINT
    root, traces = _normalize_endpoint(str(resolved_endpoint))

    resolved_environment = _first(environment, env.get("HELIOS_ENVIRONMENT"))
    if resolved_environment is not None:
        resolved_environment = str(resolved_environment).strip() or None

    if capture_content is None:
        resolved_capture = _parse_bool(
            env.get("HELIOS_CAPTURE_CONTENT"), field_name="HELIOS_CAPTURE_CONTENT"
        )
    else:
        resolved_capture = _parse_bool(capture_content, field_name="capture_content")

    resolved_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS
    try:
        resolved_timeout = float(resolved_timeout)
    except (TypeError, ValueError):
        raise HeliosConfigurationError(f"timeout must be a number (got {timeout!r})")
    if resolved_timeout <= 0:
        raise HeliosConfigurationError(f"timeout must be positive (got {resolved_timeout})")

    return HeliosConfig(
        api_key=resolved_key,
        service_name=resolved_service,
        endpoint=root,
        traces_endpoint=traces,
        environment=resolved_environment,
        capture_content=resolved_capture,
        timeout=resolved_timeout,
        headers={"Authorization": f"Bearer {resolved_key}"},
    )
