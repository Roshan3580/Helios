import { apiFetch } from "./client";
import type { BackendTrace, BackendTraceDetail, TraceListParams } from "./types";

function toQuery(params: TraceListParams): string {
  const search = new URLSearchParams();
  if (params.project_slug) search.set("project_slug", params.project_slug);
  if (params.status) search.set("status", params.status);
  if (params.model) search.set("model", params.model);
  if (params.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export async function fetchTraces(params: TraceListParams = {}): Promise<BackendTrace[]> {
  return apiFetch<BackendTrace[]>(`/v1/traces${toQuery(params)}`);
}

export async function fetchTraceDetail(traceId: string): Promise<BackendTraceDetail> {
  return apiFetch<BackendTraceDetail>(`/v1/traces/${encodeURIComponent(traceId)}`);
}
