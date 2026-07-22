/**
 * Central API base URL resolution for browser and SSR fetch paths.
 *
 * Only VITE_API_BASE_URL (public, non-secret) may configure the backend host.
 */

export type ApiUrlEnvironment = "local" | "test" | "e2e" | "staging" | "production";

export function normalizeApiBaseUrl(raw: string): string {
  const trimmed = raw.trim().replace(/\/+$/, "");
  if (!trimmed) {
    throw new Error("API base URL is empty");
  }
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error("API base URL is not a valid absolute URL");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("API base URL must use http or https");
  }
  if (parsed.username || parsed.password) {
    throw new Error("API base URL must not include credentials");
  }
  if (parsed.search || parsed.hash) {
    throw new Error("API base URL must not include query or fragment");
  }
  return `${parsed.protocol}//${parsed.host}${parsed.pathname.replace(/\/+$/, "")}`;
}

export function resolveApiBaseUrl(options: {
  configured?: string | undefined;
  environment?: ApiUrlEnvironment | string | undefined;
  defaultLocal?: string;
}): string {
  const env = (options.environment ?? "local").toLowerCase();
  const fallback = options.defaultLocal ?? "http://localhost:8000";
  const raw = (options.configured ?? "").trim() || fallback;
  const normalized = normalizeApiBaseUrl(raw);

  if (env === "staging" || env === "production") {
    if (!normalized.startsWith("https://")) {
      throw new Error("Staging/production API base URL must use HTTPS");
    }
    const host = new URL(normalized).hostname.toLowerCase();
    if (host === "localhost" || host === "127.0.0.1" || host === "::1") {
      throw new Error("Staging/production API base URL must not be loopback");
    }
  }

  return normalized;
}

/** Build-time public API URL used by browser/SSR shared client code. */
export function getConfiguredApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
  const environment = (import.meta.env.VITE_HELIOS_ENVIRONMENT as string | undefined) ?? "local";
  // Local/CI builds may omit VITE_HELIOS_ENVIRONMENT; default remains localhost.
  try {
    return resolveApiBaseUrl({ configured, environment });
  } catch {
    // Preserve historical local default when env is unset/mis-typed in CI unit builds.
    if (!configured || environment === "local" || environment === "test" || environment === "e2e") {
      return normalizeApiBaseUrl(configured || "http://localhost:8000");
    }
    throw new Error("Invalid VITE_API_BASE_URL for staging-shaped build");
  }
}
