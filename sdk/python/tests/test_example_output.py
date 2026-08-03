"""Truthful output contracts for the official batched-export examples."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def load_example(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("python_sdk_quickstart", "examples/python_sdk_quickstart/main.py"),
        ("otel_quickstart", "examples/otel_quickstart/main.py"),
    ],
)
def test_completed_flush_uses_neutral_message(name, path, capsys):
    module = load_example(name, path)
    assert module.report_export_attempt(True) == 0
    captured = capsys.readouterr()
    assert "Export completed locally" in captured.out
    assert "Check Helios to confirm trace arrival" in captured.out
    assert "exporter errors are authoritative" in captured.out.lower()
    assert not any(
        word in captured.out.lower() for word in ("success", "submitted", "sent")
    )
    assert captured.err == ""


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("python_sdk_quickstart_failure", "examples/python_sdk_quickstart/main.py"),
        ("otel_quickstart_failure", "examples/otel_quickstart/main.py"),
    ],
)
def test_incomplete_flush_is_failure_without_secret_output(
    name, path, capsys, monkeypatch
):
    module = load_example(name, path)
    secret = "hel_proj_example_secret_value_that_must_not_be_logged"
    monkeypatch.setenv("HELIOS_API_KEY", secret)
    assert module.report_export_attempt(False) == 1
    captured = capsys.readouterr()
    assert "did not complete locally" in captured.err
    assert "success" not in captured.err.lower()
    assert secret not in captured.out + captured.err


def test_unauthorized_readback_is_confirmed_failure_without_success(capsys, monkeypatch):
    module = load_example(
        "python_sdk_quickstart_unauthorized",
        "examples/python_sdk_quickstart/main.py",
    )
    secret = "hel_proj_revoked_example_value_that_must_not_be_logged"
    monkeypatch.setenv("HELIOS_API_KEY", secret)
    assert module.report_trace_verification(401) == 1
    captured = capsys.readouterr()
    assert "rejected the key with status 401" in captured.err
    assert "success" not in captured.err.lower()
    assert secret not in captured.out + captured.err


def test_success_is_reported_only_after_readback_confirmation(capsys):
    module = load_example(
        "python_sdk_quickstart_confirmed",
        "examples/python_sdk_quickstart/main.py",
    )
    assert module.report_trace_verification(200) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "Trace confirmed in Helios."
    assert captured.err == ""
