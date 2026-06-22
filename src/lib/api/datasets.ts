import { apiFetch } from "./client";
import type { BackendDatasetSummary } from "./types";

export async function fetchDatasets(projectSlug?: string): Promise<BackendDatasetSummary[]> {
  const qs = projectSlug ? `?project_slug=${encodeURIComponent(projectSlug)}` : "";
  return apiFetch<BackendDatasetSummary[]>(`/v1/datasets${qs}`);
}
