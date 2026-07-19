import { useCallback, useEffect, useRef, useState } from "react";
import {
  useHeliosAccessToken as useAccessToken,
  useHeliosAuth as useAuth,
} from "@/lib/auth/helios-auth";

import { useProjectSelection } from "@/contexts/project-selection";
import { redirectToSignIn } from "@/lib/auth/redirect-to-sign-in";
import { analyzeUserProject, UserApiError, type ProjectAnalysis } from "@/lib/api/user";

export type ProjectAnalysisStatus = "idle" | "loading" | "success" | "error";
export type ProjectNarrativeRequestStatus = "idle" | "loading";

export interface ProjectAnalysisState {
  status: ProjectAnalysisStatus;
  analysis: ProjectAnalysis | null;
  error: string | null;
  errorStatus: number | null;
  narrativeRequestStatus: ProjectNarrativeRequestStatus;
  /** Deterministic analysis only (`include_narrative=false`). */
  runAnalysis: () => void;
  /** Request the optional explanation (reruns deterministic analysis server-side). */
  generateExplanation: () => void;
  /** Rerun using the most recently selected mode. */
  rerunAnalysis: () => void;
  canRun: boolean;
}

/**
 * Explicit project-window analysis for the selected project.
 *
 * - Never auto-runs; the user must trigger it.
 * - Result lives only in React memory (no localStorage/sessionStorage).
 * - Cleared whenever the project, hours, or WorkOS organization changes and
 *   on unmount; superseded requests are aborted/ignored.
 * - Narrative is optional and never requested until generateExplanation().
 */
export function useProjectAnalysis(hours: number): ProjectAnalysisState {
  const { getAccessToken } = useAccessToken();
  const { organizationId } = useAuth();
  const { selectedProject } = useProjectSelection();

  const [status, setStatus] = useState<ProjectAnalysisStatus>("idle");
  const [analysis, setAnalysis] = useState<ProjectAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [narrativeRequestStatus, setNarrativeRequestStatus] =
    useState<ProjectNarrativeRequestStatus>("idle");

  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const lastIncludeNarrativeRef = useRef(false);
  const analysisRef = useRef<ProjectAnalysis | null>(null);

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
  }, [selectedProject?.id, organizationId, hours, reset]);

  const projectId = selectedProject?.id ?? null;

  const execute = useCallback(
    (includeNarrative: boolean) => {
      if (!projectId) return;

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
          const result = await analyzeUserProject({
            accessToken: token,
            projectRef: projectId,
            hours,
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
              message = "This project was not found in the active organization.";
            } else if (err.status === 422) {
              message =
                "The analysis request was rejected as invalid. This usually indicates a rule-contract mismatch.";
            } else {
              message = "Project analysis could not be completed.";
            }
          } else {
            message = "Project analysis could not be completed.";
          }
          // Narrative-request transport failures should not wipe existing
          // deterministic findings from a prior successful run.
          const prior = analysisRef.current;
          if (includeNarrative && prior) {
            const failed: ProjectAnalysis = {
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
    [projectId, hours, getAccessToken],
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
    canRun: Boolean(projectId),
  };
}
