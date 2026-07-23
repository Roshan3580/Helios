/**
 * Human-authenticated (WorkOS JWT) API client for /v2/user routes.
 *
 * Deliberately separate from the legacy public apiFetch client: user JWTs are
 * attached ONLY here, never to legacy/demo requests. The token is passed in by
 * the caller (obtained fresh via useAccessToken().getAccessToken() immediately
 * before the call) and is never persisted to localStorage/sessionStorage or
 * logged.
 */

import { API_BASE_URL } from "./client";

export interface UserOrganization {
  id: string | null;
  workos_org_id: string | null;
  slug: string | null;
  name: string | null;
  linked: boolean;
}

export interface UserMe {
  user_id: string;
  workos_user_id: string;
  organization: UserOrganization;
  role: string | null;
  permissions: string[];
}

export interface UserProject {
  id: string;
  slug: string;
  name: string;
  environment: string;
}

/** JSON-safe recursive value type for OTel attribute payloads. */
export type OtelJsonValue =
  | string
  | number
  | boolean
  | null
  | OtelJsonValue[]
  | { [key: string]: OtelJsonValue };

export interface OtelTraceSummary {
  trace_id: string;
  project_slug: string;
  service_name: string;
  environment: string | null;
  start_time: string;
  end_time: string;
  duration_ms: number;
  root_span_id: string | null;
  root_span_name: string | null;
  span_count: number;
  error_count: number;
  first_seen_at: string;
  last_seen_at: string;
}

export interface OtelSpan {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  kind: number;
  status_code: number;
  status_message: string | null;
  start_time: string;
  end_time: string;
  duration_ms: number;
  trace_state: string | null;
  trace_flags: number;
  resource_attributes: Record<string, OtelJsonValue>;
  scope_name: string | null;
  scope_version: string | null;
  scope_attributes: Record<string, OtelJsonValue>;
  attributes: Record<string, OtelJsonValue>;
  events: Record<string, OtelJsonValue>[];
  links: Record<string, OtelJsonValue>[];
  dropped_attributes_count: number;
  dropped_events_count: number;
  dropped_links_count: number;
}

export interface OtelTraceDetail extends OtelTraceSummary {
  spans: OtelSpan[];
}

export interface UserTraceListParams {
  limit?: number;
  service_name?: string;
  has_errors?: boolean;
}

export interface DashboardOverview {
  trace_count: number;
  error_trace_count: number;
  trace_error_rate: number;
  total_span_count: number;
  avg_duration_ms: number | null;
  p50_duration_ms: number | null;
  p95_duration_ms: number | null;
  distinct_service_count: number;
}

export interface DashboardTokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  spans_with_token_data: number;
}

export interface DashboardServiceRow {
  service_name: string;
  trace_count: number;
  error_trace_count: number;
  error_rate: number;
  avg_duration_ms: number | null;
  p50_duration_ms: number | null;
  p95_duration_ms: number | null;
  total_spans: number;
}

export interface DashboardModelRow {
  model: string;
  span_count: number;
  trace_count: number;
  input_tokens: number;
  output_tokens: number;
  error_span_count: number;
  avg_duration_ms: number | null;
}

export interface DashboardRecentError {
  trace_id: string;
  service_name: string;
  root_span_name: string | null;
  start_time: string;
  duration_ms: number;
  span_count: number;
  error_count: number;
}

export interface DashboardLatencyBucket {
  bucket_start: string;
  trace_count: number;
  error_count: number;
  avg_duration_ms: number | null;
  p95_duration_ms: number | null;
}

export interface ProjectDashboard {
  project_id: string;
  project_slug: string;
  hours: number;
  window_start: string;
  window_end: string;
  overview: DashboardOverview;
  tokens: DashboardTokenUsage;
  services: DashboardServiceRow[];
  models: DashboardModelRow[];
  recent_errors: DashboardRecentError[];
  latency_trend: DashboardLatencyBucket[];
}

export interface UserDashboardParams {
  hours?: number;
}

/** One deterministic evidence-backed finding from the trace analysis API. */
export interface AnalysisFinding {
  evidence_id: string;
  rule_id: string;
  ruleset_version: string;
  severity: "error" | "warning" | "info";
  confidence: "low" | "medium" | "high";
  category: string;
  statement: string;
  metric_name: string;
  observed_value: OtelJsonValue;
  baseline_value: OtelJsonValue | null;
  span_ids: string[];
  source_start_time: string | null;
  source_end_time: string | null;
  supporting_attributes: Record<string, OtelJsonValue>;
  trace_ui_path: string;
  span_ui_selectors: string[];
}

export interface AnalysisCoverage {
  total_spans: number;
  error_spans: number;
  spans_with_model_data: number;
  spans_with_token_data: number;
  tool_like_spans: number;
  model_like_spans: number;
  orphan_spans: number;
}

/** Optional narrative status returned with deterministic analysis. */
export type NarrativeStatus = "not_requested" | "disabled" | "complete" | "failed" | string;

export interface TraceAnalysisFindingExplanation {
  evidence_id: string;
  explanation: string;
  remediation: string;
}

export interface TraceAnalysisNarrative {
  summary: string;
  finding_explanations: TraceAnalysisFindingExplanation[];
  caveats: string[];
}

/** Response of POST /v2/user/projects/{ref}/analysis/traces/{trace_id}. */
export interface TraceAnalysis {
  analysis_version: string;
  mode: "deterministic";
  project_id: string;
  trace_id: string;
  generated_at: string;
  findings: AnalysisFinding[];
  coverage: AnalysisCoverage;
  limitations: string[];
  available_rules: string[];
  executed_rules: string[];
  narrative_status?: NarrativeStatus;
  narrative?: TraceAnalysisNarrative | null;
}

/** Half-open UTC window: start inclusive, end exclusive. */
export interface ProjectAnalysisWindow {
  start: string;
  end: string;
}

/** Browser-safe reference to one real trace cited by a project finding. */
export interface ProjectSupportingTrace {
  trace_id: string;
  service_name: string;
  root_span_name: string | null;
  start_time: string;
  duration_ms: number;
  span_count: number;
  error_count: number;
  trace_ui_path: string;
}

/** One deterministic project-window finding (ruleset project-window-v1). */
export interface ProjectFinding {
  evidence_id: string;
  rule_id: string;
  ruleset_version: string;
  severity: "error" | "warning" | "info";
  confidence: "low" | "medium" | "high";
  category: string;
  statement: string;
  metric_name: string;
  observed_value: OtelJsonValue;
  baseline_value: OtelJsonValue | null;
  current_window: ProjectAnalysisWindow;
  baseline_window: ProjectAnalysisWindow;
  entity_type: "service" | "model" | "error_signature" | "instrumentation" | "project";
  entity_label: string;
  supporting_traces: ProjectSupportingTrace[];
  supporting_span_ids: string[];
  sample_size: Record<string, number>;
  supporting_values: Record<string, OtelJsonValue>;
}

/** Factual data-coverage counts for both windows. Not a quality score. */
export interface ProjectAnalysisCoverage {
  current_trace_count: number;
  baseline_trace_count: number;
  current_span_count: number;
  baseline_span_count: number;
  current_error_trace_count: number;
  baseline_error_trace_count: number;
  services_observed: number;
  models_observed: number;
  model_like_span_count: number;
  spans_with_model_data: number;
  spans_with_token_data: number;
  tool_like_span_count: number;
  traces_without_root_span: number;
  orphan_span_count: number;
  current_sample_sparse: boolean;
  baseline_sample_sparse: boolean;
}

/** Configured caps plus whether any candidate set was actually truncated. */
export interface ProjectAnalysisBounds {
  max_findings: number;
  max_example_traces_per_finding: number;
  max_services_analyzed: number;
  max_models_analyzed: number;
  max_error_groups: number;
  max_error_span_candidates: number;
  services_truncated: boolean;
  models_truncated: boolean;
  error_groups_truncated: boolean;
  error_span_candidates_truncated: boolean;
  findings_truncated: boolean;
}

/** Request body of POST /v2/user/projects/{ref}/analysis. */
export interface ProjectAnalysisRequest {
  hours?: number;
  rules?: string[];
  include_narrative?: boolean;
}

/** Response of POST /v2/user/projects/{ref}/analysis. */
export interface ProjectAnalysis {
  analysis_version: string;
  mode: "deterministic";
  project_id: string;
  generated_at: string;
  hours: number;
  current_window: ProjectAnalysisWindow;
  baseline_window: ProjectAnalysisWindow;
  findings: ProjectFinding[];
  coverage: ProjectAnalysisCoverage;
  limitations: string[];
  available_rules: string[];
  executed_rules: string[];
  bounds: ProjectAnalysisBounds;
  narrative_status?: NarrativeStatus;
  narrative?: TraceAnalysisNarrative | null;
}

/**
 * Typed error for authenticated user API calls.
 * Never includes Authorization headers or tokens.
 */
export class UserApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly path: string,
    readonly detail?: string,
    /** Seconds from a provider Retry-After header (429), when present. */
    readonly retryAfterSeconds?: number | null,
  ) {
    super(message);
    this.name = "UserApiError";
  }
}

async function userApiFetch<T>(
  path: string,
  accessToken: string,
  init?: { method?: "GET" | "POST"; body?: unknown; signal?: AbortSignal },
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    Authorization: `Bearer ${accessToken}`,
  };
  const hasBody = init?.body !== undefined;
  if (hasBody) headers["Content-Type"] = "application/json";
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: init?.method ?? "GET",
    headers,
    body: hasBody ? JSON.stringify(init?.body) : undefined,
    signal: init?.signal,
  });
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body: unknown = await response.json();
      if (
        body &&
        typeof body === "object" &&
        "detail" in body &&
        typeof (body as { detail: unknown }).detail === "string"
      ) {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      // Ignore non-JSON error bodies; never surface raw auth material.
    }
    // Preserve a provider rate-limit hint (seconds form) for bounded backoff.
    let retryAfterSeconds: number | null = null;
    const retryAfter = response.headers.get("Retry-After");
    if (retryAfter && /^\d+$/.test(retryAfter.trim())) {
      const parsed = Number.parseInt(retryAfter.trim(), 10);
      retryAfterSeconds = Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
    }
    throw new UserApiError(
      detail || `Request failed (${response.status})`,
      response.status,
      path,
      detail,
      retryAfterSeconds,
    );
  }
  return (await response.json()) as T;
}

export function fetchUserMe(accessToken: string): Promise<UserMe> {
  return userApiFetch<UserMe>("/v2/user/me", accessToken);
}

export function fetchUserProjects(accessToken: string): Promise<UserProject[]> {
  return userApiFetch<UserProject[]>("/v2/user/projects", accessToken);
}

function tracesQuery(params: UserTraceListParams = {}): string {
  const search = new URLSearchParams();
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.service_name) search.set("service_name", params.service_name);
  if (params.has_errors != null) search.set("has_errors", String(params.has_errors));
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export function fetchUserProjectTraces(
  accessToken: string,
  projectRef: string,
  params: UserTraceListParams = {},
): Promise<OtelTraceSummary[]> {
  const encoded = encodeURIComponent(projectRef);
  return userApiFetch<OtelTraceSummary[]>(
    `/v2/user/projects/${encoded}/traces${tracesQuery(params)}`,
    accessToken,
  );
}

export function fetchUserProjectTraceDetail(
  accessToken: string,
  projectRef: string,
  traceId: string,
): Promise<OtelTraceDetail> {
  const project = encodeURIComponent(projectRef);
  const trace = encodeURIComponent(traceId);
  return userApiFetch<OtelTraceDetail>(`/v2/user/projects/${project}/traces/${trace}`, accessToken);
}

/**
 * Run the deterministic evidence analysis for one project-scoped trace.
 *
 * Explicit command (POST), but with no side effects on the server: results
 * are ephemeral and never persisted. When `rules` is omitted, all default
 * `single-trace-v1` rules run; the body stays empty so nothing undefined is
 * serialized. No retry loop — reruns are user-triggered.
 */
export function analyzeUserProjectTrace({
  accessToken,
  projectRef,
  traceId,
  rules,
  includeNarrative,
  signal,
}: {
  accessToken: string;
  projectRef: string;
  traceId: string;
  rules?: string[];
  /** When true, request an optional evidence-constrained explanation. */
  includeNarrative?: boolean;
  signal?: AbortSignal;
}): Promise<TraceAnalysis> {
  const project = encodeURIComponent(projectRef);
  const trace = encodeURIComponent(traceId);
  const body: { rules?: string[]; include_narrative?: boolean } = {};
  if (rules && rules.length > 0) body.rules = rules;
  if (includeNarrative) body.include_narrative = true;
  return userApiFetch<TraceAnalysis>(
    `/v2/user/projects/${project}/analysis/traces/${trace}`,
    accessToken,
    {
      method: "POST",
      body,
      signal,
    },
  );
}

/**
 * Run the deterministic project-window evidence analysis for one project.
 *
 * Explicit command (POST) with no server-side side effects: results are
 * ephemeral and never persisted. The token is obtained fresh by the caller;
 * there is no project API key, provider/model selection, or retry loop —
 * reruns are user-triggered.
 */
export function analyzeUserProject({
  accessToken,
  projectRef,
  hours,
  rules,
  includeNarrative,
  signal,
}: {
  accessToken: string;
  projectRef: string;
  hours?: number;
  rules?: string[];
  /** When true, request an optional evidence-constrained explanation. */
  includeNarrative?: boolean;
  signal?: AbortSignal;
}): Promise<ProjectAnalysis> {
  const project = encodeURIComponent(projectRef);
  const body: ProjectAnalysisRequest = {};
  if (hours != null) body.hours = hours;
  if (rules && rules.length > 0) body.rules = rules;
  if (includeNarrative) body.include_narrative = true;
  return userApiFetch<ProjectAnalysis>(`/v2/user/projects/${project}/analysis`, accessToken, {
    method: "POST",
    body,
    signal,
  });
}

export function fetchUserProjectDashboard(
  accessToken: string,
  projectRef: string,
  params: UserDashboardParams = {},
): Promise<ProjectDashboard> {
  const encoded = encodeURIComponent(projectRef);
  const search = new URLSearchParams();
  if (params.hours != null) search.set("hours", String(params.hours));
  const qs = search.toString();
  return userApiFetch<ProjectDashboard>(
    `/v2/user/projects/${encoded}/dashboard${qs ? `?${qs}` : ""}`,
    accessToken,
  );
}

/** Known project API-key scopes (must match backend VALID_SCOPES). */
export const PROJECT_API_KEY_SCOPES = ["traces:ingest", "traces:read"] as const;
export type ProjectApiKeyScope = (typeof PROJECT_API_KEY_SCOPES)[number];

export interface CreateUserProjectInput {
  name: string;
  slug: string;
  environment?: "production" | "staging" | "development" | "test";
}

export interface ProjectApiKeyMetadata {
  id: string;
  name: string;
  key_identifier: string;
  scopes: string[];
  created_at: string;
  revoked_at: string | null;
  status: "active" | "revoked";
}

export interface CreateProjectApiKeyInput {
  name: string;
  scopes: ProjectApiKeyScope[];
}

/**
 * One-time creation payload. `plaintext_key` must stay in React memory only
 * and must never be logged, persisted, or put in URLs.
 */
export interface CreatedProjectApiKey {
  key: ProjectApiKeyMetadata;
  plaintext_key: string;
}

export function createUserProject(
  accessToken: string,
  input: CreateUserProjectInput,
): Promise<UserProject> {
  return userApiFetch<UserProject>("/v2/user/projects", accessToken, {
    method: "POST",
    body: input,
  });
}

export function fetchUserProjectApiKeys(
  accessToken: string,
  projectRef: string,
): Promise<ProjectApiKeyMetadata[]> {
  const encoded = encodeURIComponent(projectRef);
  return userApiFetch<ProjectApiKeyMetadata[]>(
    `/v2/user/projects/${encoded}/api-keys`,
    accessToken,
  );
}

export function createUserProjectApiKey(
  accessToken: string,
  projectRef: string,
  input: CreateProjectApiKeyInput,
): Promise<CreatedProjectApiKey> {
  const encoded = encodeURIComponent(projectRef);
  return userApiFetch<CreatedProjectApiKey>(`/v2/user/projects/${encoded}/api-keys`, accessToken, {
    method: "POST",
    body: input,
  });
}

export function revokeUserProjectApiKey(
  accessToken: string,
  projectRef: string,
  keyId: string,
): Promise<ProjectApiKeyMetadata> {
  const project = encodeURIComponent(projectRef);
  const key = encodeURIComponent(keyId);
  return userApiFetch<ProjectApiKeyMetadata>(
    `/v2/user/projects/${project}/api-keys/${key}/revoke`,
    accessToken,
    { method: "POST" },
  );
}
