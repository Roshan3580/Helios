"""OpenAI auto-instrumentation via the official instrumentor (no network).

The OpenAI client is wired to a mock HTTP transport; no real OpenAI request is
made. Content capture is verified off-by-default and on-only-when-opted-in.
"""

import asyncio
import json
import logging

import pytest

from conftest import SECRET_PROMPT, make_async_openai_client, make_openai_client


def _call(client):
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": SECRET_PROMPT}],
    )


def _openai_spans(exporter):
    return [s for s in exporter.get_finished_spans() if s.attributes.get("gen_ai.operation.name")]


class TestInstrumentation:
    def test_instrumentation_succeeds_and_produces_span(self, inmemory_helios):
        helios, exporter = inmemory_helios
        helios.instrument_openai()
        _call(make_openai_client())
        spans = _openai_spans(exporter)
        assert len(spans) == 1

    def test_model_and_operation_attributes(self, inmemory_helios):
        helios, exporter = inmemory_helios
        helios.instrument_openai()
        _call(make_openai_client())
        attrs = _openai_spans(exporter)[0].attributes
        assert attrs["gen_ai.operation.name"] == "chat"
        assert attrs["gen_ai.request.model"] == "gpt-4o-mini"

    def test_token_usage_present(self, inmemory_helios):
        helios, exporter = inmemory_helios
        helios.instrument_openai()
        _call(make_openai_client())
        attrs = _openai_spans(exporter)[0].attributes
        assert attrs["gen_ai.usage.input_tokens"] == 11
        assert attrs["gen_ai.usage.output_tokens"] == 5

    def test_calling_twice_does_not_duplicate(self, inmemory_helios):
        helios, exporter = inmemory_helios
        helios.instrument_openai()
        helios.instrument_openai()  # idempotent
        _call(make_openai_client())
        assert len(_openai_spans(exporter)) == 1

    def test_async_client_produces_span(self, inmemory_helios):
        helios, exporter = inmemory_helios
        helios.instrument_openai()
        client = make_async_openai_client()

        async def run():
            return await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            )

        asyncio.run(run())
        assert len(_openai_spans(exporter)) == 1

    def test_error_response_sets_error_status(self, inmemory_helios):
        from opentelemetry.trace import StatusCode

        helios, exporter = inmemory_helios
        helios.instrument_openai()
        with pytest.raises(Exception):
            _call(make_openai_client(error=True))
        spans = exporter.get_finished_spans()
        assert spans
        assert spans[0].status.status_code == StatusCode.ERROR

    def test_content_absent_by_default(self, inmemory_helios, caplog):
        helios, exporter = inmemory_helios
        helios.instrument_openai()
        with caplog.at_level(logging.DEBUG):
            _call(make_openai_client())
        span = _openai_spans(exporter)[0]
        blob = json.dumps({k: str(v) for k, v in span.attributes.items()})
        blob += "\n" + "\n".join(
            json.dumps(dict(e.attributes)) for e in span.events
        )
        assert SECRET_PROMPT not in blob
        # Helios must not log content itself. (The OpenAI client's own DEBUG
        # logging echoes the caller's request and is outside Helios's control.)
        helios_logs = [
            r.getMessage() for r in caplog.records if r.name.startswith("helios")
        ]
        assert SECRET_PROMPT not in "\n".join(helios_logs)

    def test_content_present_after_opt_in(self, inmemory_helios):
        helios, exporter = inmemory_helios
        helios.instrument_openai(capture_content=True)
        _call(make_openai_client())
        span = _openai_spans(exporter)[0]
        blob = json.dumps({k: str(v) for k, v in span.attributes.items()})
        blob += "\n" + "\n".join(
            json.dumps(dict(e.attributes)) for e in span.events
        )
        assert SECRET_PROMPT in blob

    def test_no_api_key_in_spans(self, inmemory_helios):
        helios, exporter = inmemory_helios
        helios.instrument_openai()
        _call(make_openai_client())
        for span in exporter.get_finished_spans():
            blob = json.dumps({k: str(v) for k, v in span.attributes.items()})
            assert "sk-test-not-real" not in blob


class TestMissingExtra:
    def test_missing_openai_extra_raises_actionable_error(self, inmemory_helios, monkeypatch):
        import builtins

        helios, _ = inmemory_helios
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("opentelemetry.instrumentation.openai_v2"):
                raise ImportError("no openai instrumentor")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        from helios_sdk.errors import HeliosInstrumentationError

        with pytest.raises(HeliosInstrumentationError, match="helios-sdk\\[otel,openai\\]"):
            helios.instrument_openai()
