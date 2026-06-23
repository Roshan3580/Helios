from __future__ import annotations

import secrets
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

import httpx

from helios_sdk.errors import HeliosAPIError, HeliosConnectionError
from helios_sdk.models import SPAN_STATUSES, SPAN_TYPES, TRACE_STATUSES, SpanStatus, SpanType, TraceStatus
from helios_sdk.timing import elapsed_ms, utc_now


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(3)}"


def _validate_non_negative(name: str, value: int | float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


class SpanRecorder:
    def __init__(
        self,
        *,
        span_id: str,
        parent_span_id: str | None,
        name: str,
        span_type: SpanType,
        provider: str | None = None,
        model: str | None = None,
        status: SpanStatus = "success",
    ) -> None:
        if span_type not in SPAN_TYPES:
            raise ValueError(f"Unsupported span_type '{span_type}'")
        if status not in SPAN_STATUSES:
            raise ValueError(f"Unsupported status '{status}'")

        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.name = name
        self.span_type = span_type
        self.provider = provider
        self.model = model
        self.status = status
        self.input_preview: str | None = None
        self.output_preview: str | None = None
        self.metadata: dict[str, Any] = {}
        self.token_count: int | None = None
        self.cost_usd: float | None = None
        self.started_at = utc_now()
        self.ended_at: datetime | None = None

    def set_input(self, value: str) -> None:
        self.input_preview = value

    def set_output(self, value: str) -> None:
        self.output_preview = value

    def set_metadata(self, metadata: dict[str, Any]) -> None:
        self.metadata = metadata

    def set_tokens(self, count: int) -> None:
        _validate_non_negative("token_count", count)
        self.token_count = count

    def set_cost(self, cost_usd: float) -> None:
        _validate_non_negative("cost_usd", cost_usd)
        self.cost_usd = cost_usd

    def set_status(self, status: SpanStatus) -> None:
        if status not in SPAN_STATUSES:
            raise ValueError(f"Unsupported status '{status}'")
        self.status = status

    def finish(self) -> None:
        self.ended_at = utc_now()

    def to_payload(self) -> dict[str, Any]:
        if self.ended_at is None:
            self.finish()
        latency = elapsed_ms(self.started_at, self.ended_at)
        return {
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "span_type": self.span_type,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": latency,
            "token_count": self.token_count,
            "cost_usd": self.cost_usd,
            "status": self.status,
            "input_preview": self.input_preview,
            "output_preview": self.output_preview,
            "metadata_json": self.metadata,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
        }


class TraceBuilder:
    def __init__(
        self,
        *,
        trace_id: str,
        user_query: str,
        app_name: str,
        model: str,
        status: TraceStatus = "success",
    ) -> None:
        if status not in TRACE_STATUSES:
            raise ValueError(f"Unsupported trace status '{status}'")

        self.trace_id = trace_id
        self.user_query = user_query
        self.app_name = app_name
        self.model = model
        self.status = status
        self.root_span_id = f"{trace_id}_input"
        self._spans: list[SpanRecorder] = []
        self._started_at = utc_now()

    @contextmanager
    def span(
        self,
        name: str,
        span_type: SpanType,
        *,
        provider: str | None = None,
        model: str | None = None,
        status: SpanStatus = "success",
        parent_span_id: str | None = None,
    ) -> Iterator[SpanRecorder]:
        recorder = SpanRecorder(
            span_id=_generate_id("spn"),
            parent_span_id=parent_span_id or self.root_span_id,
            name=name,
            span_type=span_type,
            provider=provider,
            model=model,
            status=status,
        )
        try:
            yield recorder
        finally:
            recorder.finish()
            self._spans.append(recorder)

    def _ensure_root_span(self) -> None:
        if any(span.name == "user.query" for span in self._spans):
            return
        root = SpanRecorder(
            span_id=self.root_span_id,
            parent_span_id=None,
            name="user.query",
            span_type="input",
        )
        root.set_input(self.user_query)
        root.set_metadata({"source": "helios_sdk"})
        root.started_at = self._started_at
        root.finish()
        self._spans.insert(0, root)

    def to_payload(
        self,
        *,
        project_slug: str,
        project_name: str | None,
        environment: str,
    ) -> dict[str, Any]:
        self._ensure_root_span()

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        estimated_cost_usd = 0.0

        for span in self._spans:
            if span.token_count is not None:
                total_tokens += span.token_count
                if span.span_type == "llm":
                    prompt_tokens += int(span.token_count * 0.75)
                    completion_tokens += span.token_count - int(span.token_count * 0.75)
            if span.cost_usd is not None:
                estimated_cost_usd += span.cost_usd

        started_times = [span.started_at for span in self._spans]
        ended_times = [span.ended_at or span.started_at for span in self._spans]
        trace_latency = elapsed_ms(min(started_times), max(ended_times))

        return {
            "trace_id": self.trace_id,
            "project_slug": project_slug,
            "project_name": project_name,
            "environment": environment,
            "user_query": self.user_query,
            "app_name": self.app_name,
            "model": self.model,
            "status": self.status,
            "latency_ms": trace_latency,
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": round(estimated_cost_usd, 6),
            "spans": [span.to_payload() for span in self._spans],
        }

    @property
    def span_count(self) -> int:
        return len(self._spans)


class HeliosClient:
    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8000",
        project_slug: str,
        project_name: str | None = None,
        environment: str = "production",
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.project_slug = project_slug
        self.project_name = project_name
        self.environment = environment
        self.timeout = timeout

    def create_trace(
        self,
        *,
        user_query: str,
        app_name: str,
        model: str,
        status: TraceStatus = "success",
        trace_id: str | None = None,
    ) -> TraceBuilder:
        return TraceBuilder(
            trace_id=trace_id or _generate_id("trc"),
            user_query=user_query,
            app_name=app_name,
            model=model,
            status=status,
        )

    def submit_trace(self, trace: TraceBuilder) -> dict[str, Any]:
        payload = trace.to_payload(
            project_slug=self.project_slug,
            project_name=self.project_name,
            environment=self.environment,
        )
        url = f"{self.base_url}/v1/traces"

        try:
            response = httpx.post(url, json=payload, timeout=self.timeout)
        except httpx.RequestError as exc:
            raise HeliosConnectionError(
                f"Could not reach Helios at {self.base_url}. Is the backend running?"
            ) from exc

        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise HeliosAPIError(
                f"Helios rejected trace ingestion ({response.status_code}): {detail}",
                status_code=response.status_code,
            )

        return response.json()
