import { useCallback, useEffect, useRef, useState } from "react";
import { useAccessToken, useAuth } from "@workos/authkit-tanstack-react-start/client";

import { useProjectSelection } from "@/contexts/project-selection";
import { redirectToSignIn } from "@/lib/auth/redirect-to-sign-in";
import { analyzeUserProjectTrace, UserApiError, type TraceAnalysis } from "@/lib/api/user";

export type TraceAnalysisStatus = "idle" | "loading" | "success" | "error";

export interface TraceAnalysisState {
  status: TraceAnalysisStatus;
  analysis: TraceAnalysis | null;
  error: string | null;
  errorStatus: number | null;
  /** Explicit user action; never runs automatically on page load. */
  runAnalysis: () => void;
  canRun: boolean;
}

/**
 * Explicit deterministic trace analysis for the selected project.
 *
 * - Never auto-runs; the user must trigger it.
 * - Result lives only in React memory (no localStorage/sessionStorage).
 * - Cleared whenever the project, trace, or WorkOS organization changes so a
 *   stale result can never render under another resource.
 * - Superseded/unmounted requests are ignored via an abort controller plus a
 *   request-generation guard.
 */
export function useTraceAnalysis(traceId: string): TraceAnalysisState {
  const { getAccessToken } = useAccessToken();
  const { organizationId } = useAuth();
  const { selectedProject } = useProjectSelection();

  const [status, setStatus] = useState<TraceAnalysisStatus>("idle");
  const [analysis, setAnalysis] = useState<TraceAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);

  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    generationRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setStatus("idle");
    setAnalysis(null);
    setError(null);
    setErrorStatus(null);
  }, []);

  // Clear results when the project, trace, or organization changes, and on
  // unmount (also covers sign-out, which unmounts the authenticated tree).
  useEffect(() => {
    reset();
    return reset;
  }, [selectedProject?.id, traceId, organizationId, reset]);

  const projectId = selectedProject?.id ?? null;

  const runAnalysis = useCallback(() => {
    if (!projectId || !traceId) return;

    const generation = ++generationRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus("loading");
    setError(null);
    setErrorStatus(null);

    void (async () => {
      const isCurrent = () => generationRef.current === generation;
      try {
        const token = await getAccessToken();
        if (!isCurrent()) return;
        if (!token) {
          redirectToSignIn();
          setStatus("error");
          setError("Session expired. Redirecting to sign in…");
          setErrorStatus(401);
          return;
        }
        const result = await analyzeUserProjectTrace({
          accessToken: token,
          projectRef: projectId,
          traceId,
          signal: controller.signal,
        });
        if (!isCurrent()) return;
        setAnalysis(result);
        setStatus("success");
      } catch (err) {
        if (!isCurrent()) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof UserApiError && err.status === 401) {
          redirectToSignIn();
          setStatus("error");
          setError("Session expired. Redirecting to sign in…");
          setErrorStatus(401);
          return;
        }
        const statusCode = err instanceof UserApiError ? err.status : null;
        let message: string;
        if (err instanceof UserApiError) {
          if (err.status === 403) {
            message = "You do not have access to analyze this project.";
          } else if (err.status === 404) {
            message = "This trace was not found in the selected project.";
          } else if (err.status === 422) {
            message =
              "The analysis request was rejected as invalid. This usually indicates a rule-contract mismatch.";
          } else {
            message = "Trace analysis could not be completed.";
          }
        } else {
          message = "Trace analysis could not be completed.";
        }
        setAnalysis(null);
        setStatus("error");
        setError(message);
        setErrorStatus(statusCode);
      }
    })();
  }, [projectId, traceId, getAccessToken]);

  return {
    status,
    analysis,
    error,
    errorStatus,
    runAnalysis,
    canRun: Boolean(projectId && traceId),
  };
}
