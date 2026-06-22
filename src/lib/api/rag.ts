import { apiFetch } from "./client";
import type { BackendRagMetrics } from "./types";

export async function fetchRagMetrics(projectSlug?: string): Promise<BackendRagMetrics> {
  const qs = projectSlug ? `?project_slug=${encodeURIComponent(projectSlug)}` : "";
  return apiFetch<BackendRagMetrics>(`/v1/rag/metrics${qs}`);
}
