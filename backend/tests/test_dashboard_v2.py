"""Authenticated project dashboard over canonical otel_traces / otel_spans."""

from datetime import datetime, timedelta, timezone

import pytest
from opentelemetry.proto.trace.v1.trace_pb2 import Span, Status
from sqlalchemy import text

from app.models_otel import OtelSpan, OtelTrace
from app.otel_genai_attributes import (
    INPUT_TOKEN_KEYS,
    OUTPUT_TOKEN_KEYS,
    REQUEST_MODEL_KEY,
    RESPONSE_MODEL_KEY,
)
from app.services import api_key_service, organization_service, otel_dashboard_service

from otlp_helpers import (
    SPAN_ID_CHILD,
    SPAN_ID_ROOT,
    TRACE_ID_A,
    TRACE_ID_B,
    any_int,
    any_string,
    kv,
    make_request,
    make_span,
    nested_trace_spans,
    post_otlp,
)
from workos_helpers import bearer, make_token

NOW = datetime(2026, 7, 18, 18, 0, 0, tzinfo=timezone.utc)


def _create_project(db_session, client, *, slug: str, org=None):
    project = api_key_service.get_or_create_project(db_session, slug=slug)
    key = api_key_service.create_api_key(
        db_session, project=project, name="dash", scopes=["traces:ingest", "traces:read"]
    )
    if org is not None:
        organization_service.assign_project(
            db_session, organization=org, project_slug=slug
        )
    db_session.commit()
    return project, key.token


def _shift_traces_individually(
    db_session, project_id, schedule: list[tuple[str, datetime, float]]
):
    """schedule: (trace_id, start, duration_ms)."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    for trace_id, start, duration_ms in schedule:
        trace = db_session.scalar(
            select(OtelTrace)
            .where(OtelTrace.project_id == project_id, OtelTrace.trace_id == trace_id)
            .options(selectinload(OtelTrace.spans))
        )
        assert trace is not None
        dur = timedelta(milliseconds=duration_ms)
        trace.start_time = start
        trace.end_time = start + dur
        trace.first_seen_at = start
        trace.last_seen_at = start + dur
        for span in trace.spans:
            span_dur = timedelta(microseconds=span.duration_ns / 1000)
            span.start_time = start
            span.end_time = start + span_dur
    db_session.commit()


def _dashboard(client, project_ref: str, *, hours: int = 24):
    return client.get(
        f"/v2/user/projects/{project_ref}/dashboard",
        params={"hours": hours},
        headers=bearer(make_token()),
    )


class TestDashboardAuthorization:
    def test_missing_jwt_returns_401(self, client, db_session, workos_verifier, linked_org):
        project, _ = _create_project(db_session, client, slug="auth-dash", org=linked_org)
        response = client.get(f"/v2/user/projects/{project.id}/dashboard")
        assert response.status_code == 401

    def test_unlinked_organization_403(self, client, db_session, workos_verifier):
        project, _ = _create_project(db_session, client, slug="unlinked-dash")
        response = _dashboard(client, project.slug)
        assert response.status_code == 403

    def test_inaccessible_project_404(self, client, db_session, workos_verifier, linked_org):
        response = _dashboard(client, "no-such-project")
        assert response.status_code == 404

    def test_other_org_project_404(self, client, db_session, workos_verifier, linked_org):
        org2, _ = organization_service.create_organization(
            db_session,
            workos_org_id="org_01DASHOTHERORG00000000",
            slug="dash-other",
            name="Other",
        )
        db_session.commit()
        project, _ = _create_project(db_session, client, slug="theirs-dash", org=org2)
        response = _dashboard(client, project.slug)
        assert response.status_code == 404
        response = _dashboard(client, str(project.id))
        assert response.status_code == 404

    def test_query_project_param_cannot_override_path(
        self, client, db_session, workos_verifier, linked_org
    ):
        mine, token_key = _create_project(db_session, client, slug="mine-dash", org=linked_org)
        org2, _ = organization_service.create_organization(
            db_session,
            workos_org_id="org_01DASHOTHERORG00000001",
            slug="dash-other-2",
            name="Other2",
        )
        db_session.commit()
        theirs, theirs_token = _create_project(
            db_session, client, slug="theirs-dash-2", org=org2
        )
        post_otlp(
            client,
            make_request(
                [make_span(name="ok", duration_ns=10_000_000)],
                service_name="svc-a",
            ),
            token=token_key,
        )
        post_otlp(
            client,
            make_request(
                [
                    make_span(
                        trace_id=TRACE_ID_B,
                        name="other",
                        duration_ns=10_000_000,
                    )
                ],
                service_name="svc-b",
            ),
            token=theirs_token,
        )
        from sqlalchemy import select

        for proj in (mine, theirs):
            for tr in db_session.scalars(
                select(OtelTrace).where(OtelTrace.project_id == proj.id)
            ):
                tr.start_time = NOW - timedelta(hours=1)
                tr.end_time = NOW - timedelta(hours=1) + timedelta(milliseconds=10)
            db_session.commit()

        # Path selects mine; query params naming another project must be ignored.
        response = client.get(
            f"/v2/user/projects/{mine.slug}/dashboard",
            params={"hours": 24, "project_id": str(theirs.id), "project_slug": theirs.slug},
            headers=bearer(make_token()),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["project_slug"] == "mine-dash"
        assert body["overview"]["trace_count"] == 1
        assert body["services"][0]["service_name"] == "svc-a"


class TestDashboardEmptyAndBasics:
    def test_empty_window(self, client, db_session, workos_verifier, linked_org):
        project, _ = _create_project(db_session, client, slug="empty-dash", org=linked_org)
        body = _dashboard(client, project.slug).json()
        assert body["hours"] == 24
        assert body["overview"]["trace_count"] == 0
        assert body["overview"]["error_trace_count"] == 0
        assert body["overview"]["trace_error_rate"] == 0.0
        assert body["overview"]["total_span_count"] == 0
        assert body["overview"]["avg_duration_ms"] is None
        assert body["overview"]["p50_duration_ms"] is None
        assert body["overview"]["p95_duration_ms"] is None
        assert body["overview"]["distinct_service_count"] == 0
        assert body["tokens"] == {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "spans_with_token_data": 0,
        }
        assert body["services"] == []
        assert body["models"] == []
        assert body["recent_errors"] == []
        assert "estimated_cost" not in body
        assert "cost" not in body["overview"]
        assert "cost" not in body["tokens"]

    def test_one_success_and_one_error_trace(
        self, client, db_session, workos_verifier, linked_org
    ):
        project, api_token = _create_project(
            db_session, client, slug="basic-dash", org=linked_org
        )
        post_otlp(
            client,
            make_request(
                [
                    make_span(
                        name="ok.root",
                        duration_ns=100_000_000,
                        status_code=Status.STATUS_CODE_OK,
                    )
                ],
                service_name="api",
            ),
            token=api_token,
        )
        post_otlp(
            client,
            make_request(
                nested_trace_spans(TRACE_ID_B),
                service_name="api",
            ),
            token=api_token,
        )
        _shift_traces_individually(
            db_session,
            project.id,
            [
                (TRACE_ID_A.hex(), NOW - timedelta(hours=2), 100.0),
                (TRACE_ID_B.hex(), NOW - timedelta(hours=1), 50.0),
            ],
        )

        body = otel_dashboard_service.get_project_dashboard(
            db_session, project=project, hours=24, now=NOW
        )
        overview = body["overview"]
        assert overview["trace_count"] == 2
        assert overview["error_trace_count"] == 1
        assert overview["trace_error_rate"] == pytest.approx(0.5)
        assert overview["total_span_count"] == 4  # 1 + 3
        assert overview["avg_duration_ms"] == pytest.approx(75.0)
        assert overview["p50_duration_ms"] == pytest.approx(75.0)
        assert overview["p95_duration_ms"] == pytest.approx(97.5)
        assert overview["distinct_service_count"] == 1

    def test_exact_time_window_filtering(
        self, client, db_session, workos_verifier, linked_org
    ):
        project, api_token = _create_project(
            db_session, client, slug="window-dash", org=linked_org
        )
        post_otlp(
            client,
            make_request([make_span(name="inside")], service_name="svc"),
            token=api_token,
        )
        post_otlp(
            client,
            make_request(
                [make_span(trace_id=TRACE_ID_B, name="outside")],
                service_name="svc",
            ),
            token=api_token,
        )
        _shift_traces_individually(
            db_session,
            project.id,
            [
                (TRACE_ID_A.hex(), NOW - timedelta(hours=2), 10.0),
                (TRACE_ID_B.hex(), NOW - timedelta(hours=48), 10.0),
            ],
        )
        body = otel_dashboard_service.get_project_dashboard(
            db_session, project=project, hours=24, now=NOW
        )
        assert body["overview"]["trace_count"] == 1

    def test_hours_bounds(self, client, db_session, workos_verifier, linked_org):
        project, _ = _create_project(db_session, client, slug="hours-dash", org=linked_org)
        assert _dashboard(client, project.slug, hours=0).status_code == 422
        assert _dashboard(client, project.slug, hours=721).status_code == 422
        assert _dashboard(client, project.slug, hours=1).status_code == 200
        assert _dashboard(client, project.slug, hours=720).status_code == 200


class TestDashboardServices:
    def test_service_breakdown_and_ordering(
        self, client, db_session, workos_verifier, linked_org
    ):
        project, api_token = _create_project(
            db_session, client, slug="svc-dash", org=linked_org
        )
        post_otlp(
            client,
            make_request(
                [make_span(name="a", duration_ns=20_000_000)],
                service_name="bravo",
            ),
            token=api_token,
        )
        post_otlp(
            client,
            make_request(
                nested_trace_spans(TRACE_ID_B),
                service_name="alpha",
            ),
            token=api_token,
        )
        _shift_traces_individually(
            db_session,
            project.id,
            [
                (TRACE_ID_A.hex(), NOW - timedelta(hours=3), 20.0),
                (TRACE_ID_B.hex(), NOW - timedelta(hours=2), 50.0),
            ],
        )
        body = otel_dashboard_service.get_project_dashboard(
            db_session, project=project, hours=24, now=NOW
        )
        names = [s["service_name"] for s in body["services"]]
        assert names == ["alpha", "bravo"]
        alpha = body["services"][0]
        assert alpha["trace_count"] == 1
        assert alpha["error_trace_count"] == 1
        assert alpha["error_rate"] == pytest.approx(1.0)
        assert alpha["total_spans"] == 3
        assert alpha["p50_duration_ms"] == pytest.approx(50.0)
        assert alpha["p95_duration_ms"] == pytest.approx(50.0)
        bravo = body["services"][1]
        assert bravo["error_trace_count"] == 0
        assert bravo["total_spans"] == 1


class TestDashboardTokensAndModels:
    def test_request_model_tokens_and_no_fabricated_split(
        self, client, db_session, workos_verifier, linked_org
    ):
        project, api_token = _create_project(
            db_session, client, slug="tok-dash", org=linked_org
        )
        post_otlp(
            client,
            make_request(
                [
                    make_span(
                        name="chat",
                        kind=Span.SPAN_KIND_CLIENT,
                        duration_ns=40_000_000,
                        attributes=[
                            kv(REQUEST_MODEL_KEY, any_string("gpt-4o")),
                            kv(INPUT_TOKEN_KEYS[0], any_int(100)),
                            kv(OUTPUT_TOKEN_KEYS[0], any_int(25)),
                        ],
                    )
                ],
                service_name="llm",
            ),
            token=api_token,
        )
        _shift_traces_individually(
            db_session,
            project.id,
            [(TRACE_ID_A.hex(), NOW - timedelta(hours=1), 40.0)],
        )
        body = otel_dashboard_service.get_project_dashboard(
            db_session, project=project, hours=24, now=NOW
        )
        assert body["tokens"]["input_tokens"] == 100
        assert body["tokens"]["output_tokens"] == 25
        assert body["tokens"]["total_tokens"] == 125
        assert body["tokens"]["spans_with_token_data"] == 1
        # No 75/25 fabrication.
        assert body["tokens"]["input_tokens"] != int(125 * 0.75)
        assert len(body["models"]) == 1
        model = body["models"][0]
        assert model["model"] == "gpt-4o"
        assert model["span_count"] == 1
        assert model["trace_count"] == 1
        assert model["input_tokens"] == 100
        assert model["output_tokens"] == 25
        assert model["error_span_count"] == 0
        assert model["avg_duration_ms"] == pytest.approx(40.0)
        assert "cost" not in model
        assert "estimated_cost_usd" not in model

    def test_response_model_fallback_and_malformed_tokens_ignored(
        self, client, db_session, workos_verifier, linked_org
    ):
        project, api_token = _create_project(
            db_session, client, slug="tok-fallback", org=linked_org
        )
        post_otlp(
            client,
            make_request(
                [
                    make_span(
                        name="chat",
                        attributes=[
                            kv(RESPONSE_MODEL_KEY, any_string("gpt-4o-mini")),
                            kv(INPUT_TOKEN_KEYS[0], any_int(10)),
                        ],
                    ),
                    make_span(
                        span_id=SPAN_ID_CHILD,
                        parent_span_id=SPAN_ID_ROOT,
                        name="other",
                        attributes=[
                            kv(REQUEST_MODEL_KEY, any_string("claude-3.5")),
                            kv(OUTPUT_TOKEN_KEYS[0], any_int(7)),
                        ],
                    ),
                ],
                service_name="llm",
            ),
            token=api_token,
        )
        from sqlalchemy import select

        # Corrupt one token attribute after ingest.
        span = db_session.scalar(
            select(OtelSpan).where(
                OtelSpan.project_id == project.id, OtelSpan.name == "chat"
            )
        )
        attrs = dict(span.attributes)
        attrs[INPUT_TOKEN_KEYS[0]] = "not-a-number"
        span.attributes = attrs
        db_session.commit()

        _shift_traces_individually(
            db_session,
            project.id,
            [(TRACE_ID_A.hex(), NOW - timedelta(hours=1), 5.0)],
        )
        body = otel_dashboard_service.get_project_dashboard(
            db_session, project=project, hours=24, now=NOW
        )
        # Malformed input ignored; output from second span still counted.
        assert body["tokens"]["input_tokens"] == 0
        assert body["tokens"]["output_tokens"] == 7
        assert body["tokens"]["total_tokens"] == 7
        assert body["tokens"]["spans_with_token_data"] == 1
        models = {m["model"]: m for m in body["models"]}
        assert set(models) == {"gpt-4o-mini", "claude-3.5"}
        assert models["gpt-4o-mini"]["input_tokens"] == 0
        assert models["claude-3.5"]["output_tokens"] == 7

    def test_request_model_precedes_response_model(
        self, client, db_session, workos_verifier, linked_org
    ):
        project, api_token = _create_project(
            db_session, client, slug="tok-prec", org=linked_org
        )
        post_otlp(
            client,
            make_request(
                [
                    make_span(
                        name="chat",
                        attributes=[
                            kv(REQUEST_MODEL_KEY, any_string("requested")),
                            kv(RESPONSE_MODEL_KEY, any_string("responded")),
                        ],
                    )
                ],
                service_name="llm",
            ),
            token=api_token,
        )
        _shift_traces_individually(
            db_session,
            project.id,
            [(TRACE_ID_A.hex(), NOW - timedelta(hours=1), 5.0)],
        )
        body = otel_dashboard_service.get_project_dashboard(
            db_session, project=project, hours=24, now=NOW
        )
        assert [m["model"] for m in body["models"]] == ["requested"]

    def test_missing_token_attributes(self, client, db_session, workos_verifier, linked_org):
        project, api_token = _create_project(
            db_session, client, slug="tok-missing", org=linked_org
        )
        post_otlp(
            client,
            make_request(
                [
                    make_span(
                        name="chat",
                        attributes=[kv(REQUEST_MODEL_KEY, any_string("gpt-4o"))],
                    )
                ],
                service_name="llm",
            ),
            token=api_token,
        )
        _shift_traces_individually(
            db_session,
            project.id,
            [(TRACE_ID_A.hex(), NOW - timedelta(hours=1), 5.0)],
        )
        body = otel_dashboard_service.get_project_dashboard(
            db_session, project=project, hours=24, now=NOW
        )
        assert body["tokens"]["total_tokens"] == 0
        assert body["tokens"]["spans_with_token_data"] == 0
        assert body["models"][0]["input_tokens"] == 0
        assert body["models"][0]["output_tokens"] == 0


class TestDashboardRecentErrors:
    def test_recent_errors_newest_first_bounded(
        self, client, db_session, workos_verifier, linked_org
    ):
        project, api_token = _create_project(
            db_session, client, slug="err-dash", org=linked_org
        )
        # One success + several errors.
        post_otlp(
            client,
            make_request([make_span(name="ok")], service_name="svc"),
            token=api_token,
        )
        for i in range(12):
            tid = bytes.fromhex(f"{i+1:032x}")
            post_otlp(
                client,
                make_request(
                    nested_trace_spans(tid),
                    service_name="svc",
                ),
                token=api_token,
            )

        from sqlalchemy import select

        traces = list(
            db_session.scalars(
                select(OtelTrace)
                .where(OtelTrace.project_id == project.id)
                .order_by(OtelTrace.trace_id)
            )
        )
        schedule = []
        for index, trace in enumerate(traces):
            start = NOW - timedelta(hours=12) + timedelta(minutes=index)
            schedule.append((trace.trace_id, start, 30.0 + index))
        _shift_traces_individually(db_session, project.id, schedule)

        body = otel_dashboard_service.get_project_dashboard(
            db_session, project=project, hours=24, now=NOW
        )
        errors = body["recent_errors"]
        assert len(errors) == 10  # bounded
        assert all(e["error_count"] > 0 for e in errors)
        starts = [e["start_time"] for e in errors]
        assert starts == sorted(starts, reverse=True)
        for e in errors:
            assert set(e.keys()) == {
                "trace_id",
                "service_name",
                "root_span_name",
                "start_time",
                "duration_ms",
                "span_count",
                "error_count",
            }
            assert "exception_message" not in e


class TestDashboardRegressions:
    def test_user_trace_routes_still_work(
        self, client, db_session, workos_verifier, linked_org
    ):
        project, api_token = _create_project(
            db_session, client, slug="reg-traces", org=linked_org
        )
        post_otlp(client, make_request(nested_trace_spans()), token=api_token)
        rows = client.get(
            f"/v2/user/projects/{project.slug}/traces",
            headers=bearer(make_token()),
        )
        assert rows.status_code == 200
        assert len(rows.json()) == 1

    def test_machine_v2_traces_unchanged(
        self, client, db_session, workos_verifier, linked_org
    ):
        project, api_token = _create_project(
            db_session, client, slug="reg-machine", org=linked_org
        )
        post_otlp(client, make_request([make_span()]), token=api_token)
        response = client.get(
            "/v2/traces", headers={"Authorization": f"Bearer {api_token}"}
        )
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_alembic_head_unchanged(self, db_session):
        version = db_session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        assert version == "004_human_identity"

    def test_http_dashboard_endpoint(
        self, client, db_session, workos_verifier, linked_org
    ):
        project, api_token = _create_project(
            db_session, client, slug="http-dash", org=linked_org
        )
        post_otlp(
            client,
            make_request(
                [
                    make_span(
                        attributes=[
                            kv(REQUEST_MODEL_KEY, any_string("gpt-4o")),
                            kv(INPUT_TOKEN_KEYS[0], any_int(3)),
                            kv(OUTPUT_TOKEN_KEYS[0], any_int(2)),
                        ]
                    )
                ]
            ),
            token=api_token,
        )
        from sqlalchemy import select

        for tr in db_session.scalars(
            select(OtelTrace).where(OtelTrace.project_id == project.id)
        ):
            tr.start_time = datetime.now(timezone.utc) - timedelta(hours=1)
            tr.end_time = tr.start_time + timedelta(milliseconds=5)
        db_session.commit()

        response = _dashboard(client, project.id, hours=24)
        assert response.status_code == 200
        body = response.json()
        assert body["project_id"] == str(project.id)
        assert body["overview"]["trace_count"] == 1
        assert body["tokens"]["total_tokens"] == 5
        assert body["latency_trend"]

