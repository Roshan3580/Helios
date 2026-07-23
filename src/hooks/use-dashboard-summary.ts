import { useCallback, useEffect, useState } from "react";
import { useHeliosAccessToken as useAccessToken } from "@/lib/auth/helios-auth";

import { useProjectSelection } from "@/contexts/project-selection";
import { redirectToSignIn } from "@/lib/auth/redirect-to-sign-in";
import { fetchUserProjectDashboard, UserApiError, type ProjectDashboard } from "@/lib/api/user";

export type DashboardHours = 24 | 168 | 720;

export interface DashboardLoadState {
  data: ProjectDashboard | null;
  hours: DashboardHours;
  setHours: (hours: DashboardHours) => void;
  loading: boolean;
  error: string | null;
  errorStatus: number | null;
  reload: () => void;
}

/**
 * Authenticated v2 dashboard for the currently selected project.
 * Never falls back to demo data or legacy /v1/dashboard/summary.
 */
export function useDashboardSummary(): DashboardLoadState {
  const { getAccessToken } = useAccessToken();
  const {
    selectedProject,
    loading: projectLoading,
    error: projectError,
    errorStatus: projectErrorStatus,
  } = useProjectSelection();
  const [hours, setHours] = useState<DashboardHours>(24);
  const [data, setData] = useState<ProjectDashboard | null>(null);
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
      setData(null);
      setLoading(false);
      setError(projectError);
      setErrorStatus(projectErrorStatus);
      return;
    }
    if (!selectedProject) {
      setData(null);
      setLoading(false);
      setError(null);
      setErrorStatus(null);
      return;
    }

    let cancelled = false;
    const projectId = selectedProject.id;

    async function load() {
      setLoading(true);
      setError(null);
      setErrorStatus(null);
      try {
        const token = await getAccessToken();
        if (!token) {
          redirectToSignIn();
          if (!cancelled) {
            setData(null);
            setLoading(false);
            setError("Session expired. Redirecting to sign in…");
            setErrorStatus(401);
          }
          return;
        }
        const dashboard = await fetchUserProjectDashboard(token, projectId, { hours });
        if (cancelled) return;
        setData(dashboard);
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof UserApiError && err.status === 401) {
          redirectToSignIn();
          setData(null);
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
              : "Failed to load dashboard";
        setData(null);
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
  }, [projectLoading, projectError, selectedProject?.id, hours, reloadToken]);

  return { data, hours, setHours, loading, error, errorStatus, reload };
}
