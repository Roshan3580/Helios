/**
 * Project API-key management hook.
 *
 * Plaintext keys exist only in `reveal` until dismissed. They are never
 * written to storage, URLs, or logs.
 */

import { useCallback, useEffect, useState } from "react";
import { useAccessToken } from "@workos/authkit-tanstack-react-start/client";

import { redirectToSignIn } from "@/lib/auth/redirect-to-sign-in";
import {
  createUserProjectApiKey,
  fetchUserProjectApiKeys,
  revokeUserProjectApiKey,
  UserApiError,
  type CreateProjectApiKeyInput,
  type CreatedProjectApiKey,
  type ProjectApiKeyMetadata,
} from "@/lib/api/user";

export type ProjectApiKeysStatus = "idle" | "loading" | "ready" | "error";

export interface ProjectApiKeysState {
  status: ProjectApiKeysStatus;
  keys: ProjectApiKeyMetadata[];
  error: string | null;
  errorStatus: number | null;
  creating: boolean;
  revokingId: string | null;
  /** One-time reveal payload; clear with dismissReveal(). */
  reveal: CreatedProjectApiKey | null;
  reload: () => void;
  createKey: (input: CreateProjectApiKeyInput) => Promise<boolean>;
  revokeKey: (keyId: string) => Promise<boolean>;
  dismissReveal: () => void;
}

function safeErrorMessage(err: unknown): { message: string; status: number | null } {
  if (err instanceof UserApiError) {
    if (err.status === 401) return { message: "Session expired.", status: 401 };
    if (err.status === 403) {
      return { message: "You do not have access to this organization.", status: 403 };
    }
    if (err.status === 404) return { message: "Project or key not found.", status: 404 };
    if (err.status === 409) return { message: err.message, status: 409 };
    if (err.status === 422) return { message: err.message, status: 422 };
    return { message: err.message || `Request failed (${err.status})`, status: err.status };
  }
  if (err instanceof Error) return { message: err.message, status: null };
  return { message: "Request failed", status: null };
}

export function useProjectApiKeys(projectId: string | null): ProjectApiKeysState {
  const { getAccessToken } = useAccessToken();
  const [status, setStatus] = useState<ProjectApiKeysStatus>("idle");
  const [keys, setKeys] = useState<ProjectApiKeyMetadata[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [reveal, setReveal] = useState<CreatedProjectApiKey | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const dismissReveal = useCallback(() => setReveal(null), []);

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    setReveal(null);
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    if (!projectId) {
      setStatus("idle");
      setKeys([]);
      setError(null);
      setErrorStatus(null);
      return;
    }

    async function load() {
      setStatus("loading");
      setError(null);
      setErrorStatus(null);
      try {
        const token = await getAccessToken();
        if (!token) {
          redirectToSignIn();
          return;
        }
        const rows = await fetchUserProjectApiKeys(token, projectId as string);
        if (cancelled) return;
        setKeys(rows);
        setStatus("ready");
      } catch (err) {
        if (cancelled) return;
        if (err instanceof UserApiError && err.status === 401) {
          redirectToSignIn();
          return;
        }
        const safe = safeErrorMessage(err);
        setKeys([]);
        setStatus("error");
        setError(safe.message);
        setErrorStatus(safe.status);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [projectId, reloadToken, getAccessToken]);

  const createKey = useCallback(
    async (input: CreateProjectApiKeyInput): Promise<boolean> => {
      if (!projectId || creating) return false;
      setCreating(true);
      setError(null);
      setErrorStatus(null);
      try {
        const token = await getAccessToken();
        if (!token) {
          redirectToSignIn();
          return false;
        }
        const created = await createUserProjectApiKey(token, projectId, input);
        setReveal(created);
        const rows = await fetchUserProjectApiKeys(token, projectId);
        setKeys(rows);
        setStatus("ready");
        return true;
      } catch (err) {
        if (err instanceof UserApiError && err.status === 401) {
          redirectToSignIn();
          return false;
        }
        const safe = safeErrorMessage(err);
        setError(safe.message);
        setErrorStatus(safe.status);
        return false;
      } finally {
        setCreating(false);
      }
    },
    [projectId, creating, getAccessToken],
  );

  const revokeKey = useCallback(
    async (keyId: string): Promise<boolean> => {
      if (!projectId || revokingId) return false;
      setRevokingId(keyId);
      setError(null);
      setErrorStatus(null);
      try {
        const token = await getAccessToken();
        if (!token) {
          redirectToSignIn();
          return false;
        }
        await revokeUserProjectApiKey(token, projectId, keyId);
        const rows = await fetchUserProjectApiKeys(token, projectId);
        setKeys(rows);
        setStatus("ready");
        return true;
      } catch (err) {
        if (err instanceof UserApiError && err.status === 401) {
          redirectToSignIn();
          return false;
        }
        const safe = safeErrorMessage(err);
        setError(safe.message);
        setErrorStatus(safe.status);
        return false;
      } finally {
        setRevokingId(null);
      }
    },
    [projectId, revokingId, getAccessToken],
  );

  return {
    status,
    keys,
    error,
    errorStatus,
    creating,
    revokingId,
    reveal,
    reload,
    createKey,
    revokeKey,
    dismissReveal,
  };
}
