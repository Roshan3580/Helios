import { describe, expect, test } from "bun:test";

import type { OtelTraceSummary } from "@/lib/api/user";
import {
  beginTelemetryCheck,
  completeTelemetryCheck,
  failTelemetryCheck,
  hasOpenedTraces,
  initialTelemetryProgress,
  markTracesOpened,
  mayCheckTelemetry,
  type OnboardingStorage,
} from "./trace-progress";

const TRACE: OtelTraceSummary = {
  trace_id: "00000000000000000000000000000001",
  project_slug: "project-one",
  service_name: "test-service",
  environment: "test",
  start_time: "2026-08-02T00:00:00Z",
  end_time: "2026-08-02T00:00:01Z",
  duration_ms: 1000,
  root_span_id: "0000000000000001",
  root_span_name: "test-root",
  span_count: 1,
  error_count: 0,
  first_seen_at: "2026-08-02T00:00:00Z",
  last_seen_at: "2026-08-02T00:00:01Z",
};

function memoryStorage(): OnboardingStorage {
  const values = new Map<string, string>();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
}

describe("first-trace onboarding progress", () => {
  test("a project with zero traces remains incomplete", () => {
    const checking = beginTelemetryCheck(initialTelemetryProgress("project-one"), "project-one");
    expect(completeTelemetryCheck(checking, "project-one", [])).toEqual({
      projectId: "project-one",
      phase: "none",
      trace: null,
      error: null,
    });
  });

  test("a stored trace completes the step on route load", () => {
    const checking = beginTelemetryCheck(initialTelemetryProgress("project-one"), "project-one");
    const complete = completeTelemetryCheck(checking, "project-one", [TRACE]);
    expect(complete.phase).toBe("received");
    expect(complete.trace?.trace_id).toBe(TRACE.trace_id);
  });

  test("manual refresh observes a trace that arrived after the initial empty load", () => {
    const empty = completeTelemetryCheck(
      beginTelemetryCheck(initialTelemetryProgress("project-one"), "project-one"),
      "project-one",
      [],
    );
    const refreshed = completeTelemetryCheck(
      beginTelemetryCheck(empty, "project-one"),
      "project-one",
      [TRACE],
    );
    expect(refreshed.phase).toBe("received");
  });

  test("a refresh error preserves the last trustworthy trace state", () => {
    const received = completeTelemetryCheck(
      beginTelemetryCheck(initialTelemetryProgress("project-one"), "project-one"),
      "project-one",
      [TRACE],
    );
    const failed = failTelemetryCheck(
      beginTelemetryCheck(received, "project-one"),
      "project-one",
      "Unable to check telemetry",
    );
    expect(failed.phase).toBe("error");
    expect(failed.trace?.trace_id).toBe(TRACE.trace_id);
  });

  test("a stale response cannot leak completion into another project", () => {
    const projectTwo = initialTelemetryProgress("project-two");
    expect(completeTelemetryCheck(projectTwo, "project-one", [TRACE])).toBe(projectTwo);
    expect(failTelemetryCheck(projectTwo, "project-one", "stale error")).toBe(projectTwo);
  });

  test("requests are blocked until token readiness and project selection", () => {
    expect(mayCheckTelemetry(false, "project-one")).toBe(false);
    expect(mayCheckTelemetry(true, null)).toBe(false);
    expect(mayCheckTelemetry(true, "project-one")).toBe(true);
  });
});

describe("open-traces completion", () => {
  test("opening traces persists across route navigation and browser refresh", () => {
    const storage = memoryStorage();
    expect(hasOpenedTraces("project-one", storage)).toBe(false);
    markTracesOpened("project-one", storage);
    expect(hasOpenedTraces("project-one", storage)).toBe(true);
    expect(hasOpenedTraces("project-one", storage)).toBe(true);
  });

  test("completion is scoped to the selected project", () => {
    const storage = memoryStorage();
    markTracesOpened("project-one", storage);
    expect(hasOpenedTraces("project-one", storage)).toBe(true);
    expect(hasOpenedTraces("project-two", storage)).toBe(false);
  });

  test("trace existence does not mark the open-traces step", () => {
    const storage = memoryStorage();
    const received = completeTelemetryCheck(
      beginTelemetryCheck(initialTelemetryProgress("project-one"), "project-one"),
      "project-one",
      [TRACE],
    );
    expect(received.trace).not.toBeNull();
    expect(hasOpenedTraces("project-one", storage)).toBe(false);
  });

  test("storage failures fail closed without breaking navigation", () => {
    const storage: OnboardingStorage = {
      getItem: () => {
        throw new Error("unavailable");
      },
      setItem: () => {
        throw new Error("unavailable");
      },
    };
    expect(hasOpenedTraces("project-one", storage)).toBe(false);
    expect(() => markTracesOpened("project-one", storage)).not.toThrow();
  });
});
