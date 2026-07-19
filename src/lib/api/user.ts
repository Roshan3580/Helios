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
  ) {
    super(message);
    this.name = "UserApiError";
  }
}

async function userApiFetch<T>(path: string, accessToken: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
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
    throw new UserApiError(
      detail || `Request failed (${response.status})`,
      response.status,
      path,
      detail,
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
