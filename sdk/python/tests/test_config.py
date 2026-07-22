"""Configuration resolution, validation, precedence, and secret hygiene."""

import logging

import pytest

from helios_sdk.config import DEFAULT_ENDPOINT, resolve_config
from helios_sdk.errors import HeliosConfigurationError


def test_explicit_configuration():
    c = resolve_config(
        api_key="hel_proj_abc_secret",
        service_name="svc",
        endpoint="https://helios.example",
        environment="prod",
        capture_content=True,
        timeout=5.0,
        env={},
    )
    assert c.service_name == "svc"
    assert c.endpoint == "https://helios.example"
    assert c.traces_endpoint == "https://helios.example/v1/otlp/traces"
    assert c.environment == "prod"
    assert c.capture_content is True
    assert c.timeout == 5.0
    assert c.headers["Authorization"] == "Bearer hel_proj_abc_secret"


def test_environment_based_configuration():
    env = {
        "HELIOS_API_KEY": "envkey",
        "HELIOS_SERVICE_NAME": "env-svc",
        "HELIOS_ENDPOINT": "https://env.example",
        "HELIOS_ENVIRONMENT": "staging",
        "HELIOS_CAPTURE_CONTENT": "true",
    }
    c = resolve_config(env=env)
    assert c.service_name == "env-svc"
    assert c.endpoint == "https://env.example"
    assert c.environment == "staging"
    assert c.capture_content is True


def test_explicit_overrides_environment():
    env = {"HELIOS_API_KEY": "envkey", "HELIOS_SERVICE_NAME": "env-svc"}
    c = resolve_config(api_key="explicit", service_name="explicit-svc", env=env)
    assert c.api_key == "explicit"
    assert c.service_name == "explicit-svc"


def test_otel_service_name_fallback():
    env = {"HELIOS_API_KEY": "k", "OTEL_SERVICE_NAME": "otel-svc"}
    c = resolve_config(env=env)
    assert c.service_name == "otel-svc"


def test_missing_api_key_raises():
    with pytest.raises(HeliosConfigurationError, match="api_key"):
        resolve_config(service_name="svc", env={})


def test_missing_service_name_raises():
    with pytest.raises(HeliosConfigurationError, match="service_name"):
        resolve_config(api_key="k", env={})


def test_default_endpoint():
    c = resolve_config(api_key="k", service_name="s", env={})
    assert c.endpoint == DEFAULT_ENDPOINT
    assert c.traces_endpoint == f"{DEFAULT_ENDPOINT}/v1/otlp/traces"


def test_endpoint_normalization_trailing_slash():
    c = resolve_config(api_key="k", service_name="s", endpoint="http://h:8000/", env={})
    assert c.traces_endpoint == "http://h:8000/v1/otlp/traces"


def test_endpoint_normalization_already_full_path():
    c = resolve_config(
        api_key="k", service_name="s", endpoint="http://h:8000/v1/otlp/traces", env={}
    )
    assert c.traces_endpoint == "http://h:8000/v1/otlp/traces"


def test_invalid_endpoint_scheme_raises():
    with pytest.raises(HeliosConfigurationError, match="http"):
        resolve_config(api_key="k", service_name="s", endpoint="ftp://h", env={})


def test_authorization_header_construction():
    c = resolve_config(api_key="my-token", service_name="s", env={})
    assert c.headers == {"Authorization": "Bearer my-token"}


def test_content_capture_defaults_off():
    c = resolve_config(api_key="k", service_name="s", env={})
    assert c.capture_content is False


def test_content_capture_explicit_opt_in():
    assert resolve_config(api_key="k", service_name="s", capture_content=True, env={}).capture_content
    c = resolve_config(api_key="k", service_name="s", env={"HELIOS_CAPTURE_CONTENT": "1"})
    assert c.capture_content is True


def test_invalid_boolean_raises():
    with pytest.raises(HeliosConfigurationError, match="boolean"):
        resolve_config(
            api_key="k", service_name="s", env={"HELIOS_CAPTURE_CONTENT": "maybe"}
        )


def test_invalid_timeout_raises():
    with pytest.raises(HeliosConfigurationError, match="positive"):
        resolve_config(api_key="k", service_name="s", timeout=0, env={})
    with pytest.raises(HeliosConfigurationError):
        resolve_config(api_key="k", service_name="s", timeout="soon", env={})


def test_api_key_absent_from_repr():
    c = resolve_config(api_key="super-secret-token", service_name="s", env={})
    assert "super-secret-token" not in repr(c)
    assert "super-secret-token" not in str(c)
    assert "***" in repr(c)


def test_api_key_absent_from_config_error(caplog):
    with caplog.at_level(logging.DEBUG):
        try:
            resolve_config(
                api_key="leak-token", service_name="s", timeout=-1, env={}
            )
        except HeliosConfigurationError as exc:
            assert "leak-token" not in str(exc)
