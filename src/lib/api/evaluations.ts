import { apiFetch } from "./client";
import type { BackendEvaluationRun } from "./types";

export async function fetchEvaluations(projectSlug?: string): Promise<BackendEvaluationRun[]> {
  const qs = projectSlug ? `?project_slug=${encodeURIComponent(projectSlug)}` : "";
  return apiFetch<BackendEvaluationRun[]>(`/v1/evaluations${qs}`);
}
