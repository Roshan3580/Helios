import { ApiError } from "./types";

const DEFAULT_TIMEOUT_MS = 8_000;

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** When not explicitly `"false"`, demo mode stays enabled (default). */
export const IS_DEMO_MODE = import.meta.env.VITE_HELIOS_DEMO_MODE !== "false";

type ApiFetchOptions = RequestInit & {
  timeout?: number;
};

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { timeout = DEFAULT_TIMEOUT_MS, ...init } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => response.statusText);
      throw new ApiError(detail || `Request failed (${response.status})`, response.status);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("Request timed out", 408);
    }
    throw new ApiError(error instanceof Error ? error.message : "Network error", 0);
  } finally {
    clearTimeout(timer);
  }
}
