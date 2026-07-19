import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  useHeliosAccessToken as useAccessToken,
  useHeliosAuth as useAuth,
} from "@/lib/auth/helios-auth";

import { redirectToSignIn } from "@/lib/auth/redirect-to-sign-in";
import { fetchUserProjects, UserApiError, type UserProject } from "@/lib/api/user";

const STORAGE_KEY = "helios.selectedProjectId";

export interface ProjectSelectionState {
  projects: UserProject[];
  selectedProject: UserProject | null;
  selectProject: (projectId: string) => void;
  /** Alias for reload — refresh authorized project list from the API. */
  refreshProjects: () => void;
  loading: boolean;
  error: string | null;
  errorStatus: number | null;
  reload: () => void;
}

const ProjectSelectionContext = createContext<ProjectSelectionState | null>(null);

function readPersistedProjectId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistProjectId(projectId: string | null): void {
  try {
    if (projectId) localStorage.setItem(STORAGE_KEY, projectId);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore storage failures (private mode, quota).
  }
}

function resolveSelection(projects: UserProject[], preferredId: string | null): string | null {
  if (preferredId && projects.some((project) => project.id === preferredId)) {
    return preferredId;
  }
  return projects[0]?.id ?? null;
}

export function ProjectSelectionProvider({ children }: { children: ReactNode }) {
  const { getAccessToken } = useAccessToken();
  const { organizationId } = useAuth();
  const [projects, setProjects] = useState<UserProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      setErrorStatus(null);
      try {
        const token = await getAccessToken();
        if (!token) {
          if (!cancelled) {
            setProjects([]);
            setSelectedProjectId(null);
            setLoading(false);
            setError("not authenticated");
            setErrorStatus(401);
          }
          redirectToSignIn();
          return;
        }
        const rows = await fetchUserProjects(token);
        if (cancelled) return;
        const preferred = readPersistedProjectId();
        const nextId = resolveSelection(rows, preferred);
        if (preferred && preferred !== nextId) {
          persistProjectId(nextId);
        } else if (nextId && !preferred) {
          persistProjectId(nextId);
        }
        setProjects(rows);
        setSelectedProjectId(nextId);
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof UserApiError && err.status === 401) {
          redirectToSignIn();
          setProjects([]);
          setSelectedProjectId(null);
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
              : "Failed to load projects";
        setProjects([]);
        setSelectedProjectId(null);
        setLoading(false);
        setError(message);
        setErrorStatus(status);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
    // Refetch when WorkOS organization changes or an explicit reload is requested.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organizationId, reloadToken]);

  const selectProject = useCallback((projectId: string) => {
    setSelectedProjectId((current) => {
      if (current === projectId) return current;
      persistProjectId(projectId);
      return projectId;
    });
  }, []);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );

  const value = useMemo<ProjectSelectionState>(
    () => ({
      projects,
      selectedProject,
      selectProject,
      refreshProjects: reload,
      loading,
      error,
      errorStatus,
      reload,
    }),
    [projects, selectedProject, selectProject, loading, error, errorStatus, reload],
  );

  return (
    <ProjectSelectionContext.Provider value={value}>{children}</ProjectSelectionContext.Provider>
  );
}

export function useProjectSelection(): ProjectSelectionState {
  const ctx = useContext(ProjectSelectionContext);
  if (!ctx) {
    throw new Error("useProjectSelection must be used within ProjectSelectionProvider");
  }
  return ctx;
}
