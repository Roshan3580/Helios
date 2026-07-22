import { useCallback, useEffect, useState } from "react";
import { useHeliosAccessToken as useAccessToken } from "@/lib/auth/helios-auth";

import { useProjectSelection } from "@/contexts/project-selection";
import { redirectToSignIn } from "@/lib/auth/redirect-to-sign-in";
import { fetchUserProjectTraces, UserApiError, type OtelTraceSummary } from "@/lib/api/user";

export interface TraceListFilters {
  serviceName: string;
  errorsOnly: boolean;
  limit: number;
}

export interface TracesLoadState {
  traces: OtelTraceSummary[];
  loading: boolean;
  error: string | null;
  errorStatus: number | null;
  reload: () => void;
}

const DEFAULT_FILTERS: TraceListFilters = {
  serviceName: "",
  errorsOnly: false,
  limit: 50,
};

/**
 * Authenticated v2 trace list for the currently selected project.
 * Never falls back to demo data.
 */
export function useTraceList(filters: TraceListFilters = DEFAULT_FILTERS): TracesLoadState {
  const { getAccessToken } = useAccessToken();
  const { selectedProject, loading: projectLoading, error: projectError } = useProjectSelection();
  const [traces, setTraces] = useState<OtelTraceSummary[]>([]);
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
      setTraces([]);
      setLoading(false);
      setError(projectError);
      setErrorStatus(null);
      return;
    }
    if (!selectedProject) {
      setTraces([]);
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
            setTraces([]);
            setLoading(false);
            setError("Session expired. Redirecting to sign in…");
            setErrorStatus(401);
          }
          return;
        }
        const rows = await fetchUserProjectTraces(token, selectedProject!.id, {
          limit: filters.limit,
          service_name: filters.serviceName.trim() || undefined,
          has_errors: filters.errorsOnly ? true : undefined,
        });
        if (cancelled) return;
        setTraces(rows);
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof UserApiError && err.status === 401) {
          redirectToSignIn();
          setTraces([]);
          setLoading(false);
          setError("Session expired. Redirecting to sign in…");
          setErrorStatus(401);
          return;
        }
        const status = err instanceof UserApiError ? err.status : null;
        const message =
          err instanceof UserApiError
            ? err.status === 403
              ? "You do not have access to this organization or project."
              : err.message
            : err instanceof Error
              ? err.message
              : "Failed to load traces";
        setTraces([]);
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
  }, [
    projectLoading,
    projectError,
    selectedProject?.id,
    filters.serviceName,
    filters.errorsOnly,
    filters.limit,
    reloadToken,
  ]);

  return { traces, loading, error, errorStatus, reload };
}
