import { useCallback, useEffect, useState } from "react";
import { useHeliosAccessToken as useAccessToken } from "@/lib/auth/helios-auth";

import { useProjectSelection } from "@/contexts/project-selection";
import { redirectToSignIn } from "@/lib/auth/redirect-to-sign-in";
import { fetchUserProjectTraceDetail, UserApiError, type OtelTraceDetail } from "@/lib/api/user";

export interface TraceDetailLoadState {
  trace: OtelTraceDetail | null;
  loading: boolean;
  error: string | null;
  errorStatus: number | null;
  reload: () => void;
}

/**
 * Authenticated v2 trace detail for the currently selected project.
 * Never falls back to demo data or fabricated panels.
 */
export function useTraceDetail(traceId: string): TraceDetailLoadState {
  const { getAccessToken } = useAccessToken();
  const {
    selectedProject,
    loading: projectLoading,
    error: projectError,
    errorStatus: projectErrorStatus,
  } = useProjectSelection();
  const [trace, setTrace] = useState<OtelTraceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    if (projectLoading) {
      setLoading(true);
      return;
    }
    if (projectError) {
      setTrace(null);
      setLoading(false);
      setError(projectError);
      setErrorStatus(projectErrorStatus);
      return;
    }
    if (!selectedProject) {
      setTrace(null);
      setLoading(false);
      setError(null);
      setErrorStatus(null);
      return;
    }

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      setErrorStatus(null);
      try {
        const token = await getAccessToken();
        if (!token) {
          redirectToSignIn();
          if (!cancelled) {
            setTrace(null);
            setLoading(false);
            setError("Session expired. Redirecting to sign in…");
            setErrorStatus(401);
          }
          return;
        }
        const detail = await fetchUserProjectTraceDetail(token, selectedProject!.id, traceId);
        if (cancelled) return;
        setTrace(detail);
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof UserApiError && err.status === 401) {
          redirectToSignIn();
          setTrace(null);
          setLoading(false);
          setError("Session expired. Redirecting to sign in…");
          setErrorStatus(401);
          return;
        }
        const status = err instanceof UserApiError ? err.status : null;
        let message: string;
        if (err instanceof UserApiError) {
          if (err.status === 403) {
            message = "You do not have access to this organization or project.";
          } else if (err.status === 404) {
            message = "This trace was not found in the selected project.";
          } else {
            message = err.message;
          }
        } else {
          message = err instanceof Error ? err.message : "Failed to load trace";
        }
        setTrace(null);
        setLoading(false);
        setError(message);
        setErrorStatus(status);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectLoading, projectError, selectedProject?.id, traceId, reloadToken]);

  return { trace, loading, error, errorStatus, reload };
}
