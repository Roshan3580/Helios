import { apiFetch } from "./client";
import type { BackendPromptVersion } from "./types";

export async function fetchPrompts(projectSlug?: string): Promise<BackendPromptVersion[]> {
  const qs = projectSlug ? `?project_slug=${encodeURIComponent(projectSlug)}` : "";
  return apiFetch<BackendPromptVersion[]>(`/v1/prompts${qs}`);
}
