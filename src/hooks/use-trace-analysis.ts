import { useCallback, useEffect, useRef, useState } from "react";
import { useAccessToken, useAuth } from "@workos/authkit-tanstack-react-start/client";

import { useProjectSelection } from "@/contexts/project-selection";
import { redirectToSignIn } from "@/lib/auth/redirect-to-sign-in";
import { analyzeUserProjectTrace, UserApiError, type TraceAnalysis } from "@/lib/api/user";

export type TraceAnalysisStatus = "idle" | "loading" | "success" | "error";
export type NarrativeRequestStatus = "idle" | "loading";

export interface TraceAnalysisState {
  status: TraceAnalysisStatus;
  analysis: TraceAnalysis | null;
  error: string | null;
  errorStatus: number | null;
  narrativeRequestStatus: NarrativeRequestStatus;
  /** Deterministic analysis only (`include_narrative=false`). */
  runAnalysis: () => void;
  /** Request optional narrative explanation (reruns deterministic analysis server-side). */
  generateExplanation: () => void;
  /** Rerun using the most recently selected mode. */
  rerunAnalysis: () => void;
  canRun: boolean;
}

/**
 * Explicit deterministic trace analysis for the selected project.
 *
 * - Never auto-runs; the user must trigger it.
 * - Result lives only in React memory (no localStorage/sessionStorage).
 * - Cleared whenever the project, trace, or WorkOS organization changes.
 * - Narrative is optional and never requested until generateExplanation().
 */
export function useTraceAnalysis(traceId: string): TraceAnalysisState {
  const { getAccessToken } = useAccessToken();
  const { organizationId } = useAuth();
  const { selectedProject } = useProjectSelection();

  const [status, setStatus] = useState<TraceAnalysisStatus>("idle");
  const [analysis, setAnalysis] = useState<TraceAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [narrativeRequestStatus, setNarrativeRequestStatus] =
    useState<NarrativeRequestStatus>("idle");

  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const lastIncludeNarrativeRef = useRef(false);
  const analysisRef = useRef<TraceAnalysis | null>(null);

  const reset = useCallback(() => {
    generationRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    lastIncludeNarrativeRef.current = false;
    analysisRef.current = null;
    setStatus("idle");
    setAnalysis(null);
    setError(null);
    setErrorStatus(null);
    setNarrativeRequestStatus("idle");
  }, []);

  useEffect(() => {
    reset();
    return reset;
  }, [selectedProject?.id, traceId, organizationId, reset]);

  const projectId = selectedProject?.id ?? null;

  const execute = useCallback(
    (includeNarrative: boolean) => {
      if (!projectId || !traceId) return;

      const generation = ++generationRef.current;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      lastIncludeNarrativeRef.current = includeNarrative;

      if (includeNarrative) {
        setNarrativeRequestStatus("loading");
      } else {
        setStatus("loading");
        setError(null);
        setErrorStatus(null);
        setNarrativeRequestStatus("idle");
      }

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
            setNarrativeRequestStatus("idle");
            return;
          }
          const result = await analyzeUserProjectTrace({
            accessToken: token,
            projectRef: projectId,
            traceId,
            includeNarrative,
            signal: controller.signal,
          });
          if (!isCurrent()) return;
          analysisRef.current = result;
          setAnalysis(result);
          setStatus("success");
          setError(null);
          setErrorStatus(null);
          setNarrativeRequestStatus("idle");
        } catch (err) {
          if (!isCurrent()) return;
          if (err instanceof DOMException && err.name === "AbortError") return;
          if (err instanceof UserApiError && err.status === 401) {
            redirectToSignIn();
            setStatus("error");
            setError("Session expired. Redirecting to sign in…");
            setErrorStatus(401);
            setNarrativeRequestStatus("idle");
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
          // Narrative-request transport failures should not wipe existing
          // deterministic findings from a prior successful run.
          const prior = analysisRef.current;
          if (includeNarrative && prior) {
            const failed: TraceAnalysis = {
              ...prior,
              narrative_status: "failed",
              narrative: null,
            };
            analysisRef.current = failed;
            setAnalysis(failed);
            setNarrativeRequestStatus("idle");
            return;
          }
          analysisRef.current = null;
          setAnalysis(null);
          setStatus("error");
          setError(message);
          setErrorStatus(statusCode);
          setNarrativeRequestStatus("idle");
        }
      })();
    },
    [projectId, traceId, getAccessToken],
  );

  const runAnalysis = useCallback(() => execute(false), [execute]);
  const generateExplanation = useCallback(() => execute(true), [execute]);
  const rerunAnalysis = useCallback(() => execute(lastIncludeNarrativeRef.current), [execute]);

  return {
    status,
    analysis,
    error,
    errorStatus,
    narrativeRequestStatus,
    runAnalysis,
    generateExplanation,
    rerunAnalysis,
    canRun: Boolean(projectId && traceId),
  };
}
