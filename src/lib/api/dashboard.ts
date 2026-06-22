import { apiFetch } from "./client";
import type { BackendDashboardSummary } from "./types";

export async function fetchDashboardSummary(
  projectSlug?: string,
): Promise<BackendDashboardSummary> {
  const qs = projectSlug ? `?project_slug=${encodeURIComponent(projectSlug)}` : "";
  return apiFetch<BackendDashboardSummary>(`/v1/dashboard/summary${qs}`);
}
