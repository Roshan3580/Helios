import type { OtelTraceSummary } from "@/lib/api/user";

const TRACE_VIEWED_KEY_PREFIX = "helios.onboarding.traceViewed.";

export interface OnboardingStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export type TelemetryCheckPhase = "idle" | "checking" | "none" | "received" | "error";

export interface TelemetryProgress {
  projectId: string | null;
  phase: TelemetryCheckPhase;
  trace: OtelTraceSummary | null;
  error: string | null;
}

function browserStorage(): OnboardingStorage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function traceViewedKey(projectId: string): string {
  return `${TRACE_VIEWED_KEY_PREFIX}${encodeURIComponent(projectId)}`;
}

export function hasOpenedTraces(
  projectId: string | null,
  storage: OnboardingStorage | null = browserStorage(),
): boolean {
  if (!projectId || !storage) return false;
  try {
    return storage.getItem(traceViewedKey(projectId)) === "1";
  } catch {
    return false;
  }
}

export function markTracesOpened(
  projectId: string | null,
  storage: OnboardingStorage | null = browserStorage(),
): void {
  if (!projectId || !storage) return;
  try {
    storage.setItem(traceViewedKey(projectId), "1");
  } catch {
    // Storage may be unavailable in private mode or when quota is exhausted.
  }
}

export function initialTelemetryProgress(projectId: string | null): TelemetryProgress {
  return { projectId, phase: "idle", trace: null, error: null };
}

export function beginTelemetryCheck(
  current: TelemetryProgress,
  projectId: string,
): TelemetryProgress {
  return {
    projectId,
    phase: "checking",
    trace: current.projectId === projectId ? current.trace : null,
    error: null,
  };
}

export function completeTelemetryCheck(
  current: TelemetryProgress,
  projectId: string,
  traces: OtelTraceSummary[],
): TelemetryProgress {
  if (current.projectId !== projectId) return current;
  const trace = traces[0] ?? null;
  return {
    projectId,
    phase: trace ? "received" : "none",
    trace,
    error: null,
  };
}

export function failTelemetryCheck(
  current: TelemetryProgress,
  projectId: string,
  message: string,
): TelemetryProgress {
  if (current.projectId !== projectId) return current;
  return {
    projectId,
    phase: "error",
    trace: current.trace,
    error: message,
  };
}

export function pauseTelemetryCheck(
  current: TelemetryProgress,
  projectId: string,
): TelemetryProgress {
  if (current.projectId !== projectId) return current;
  return { ...current, phase: "idle", error: null };
}

export function mayCheckTelemetry(ready: boolean, projectId: string | null): boolean {
  return ready && Boolean(projectId);
}
