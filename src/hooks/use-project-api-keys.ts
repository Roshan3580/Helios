/**
 * Project API-key management hook.
 *
 * Plaintext keys exist only in `reveal` until dismissed. They are never
 * written to storage, URLs, or logs.
 */

import { useCallback, useEffect, useState } from "react";

import { useAuthorizedRequest } from "@/lib/api/authorized-request";
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
  const { run } = useAuthorizedRequest();
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
        const rows = await run((token) => fetchUserProjectApiKeys(token, projectId as string));
        if (cancelled) return;
        setKeys(rows);
        setStatus("ready");
      } catch (err) {
        if (cancelled) return;
        // A bounded 401 was already reported to central session recovery by
        // run(); surface a neutral state and never redirect from here.
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
  }, [projectId, reloadToken, run]);

  const createKey = useCallback(
    async (input: CreateProjectApiKeyInput): Promise<boolean> => {
      if (!projectId || creating) return false;
      setCreating(true);
      setError(null);
      setErrorStatus(null);
      try {
        // Each call is wrapped independently so a 401 refresh+retry never
        // re-runs the non-idempotent create after the follow-up read fails.
        const created = await run((token) => createUserProjectApiKey(token, projectId, input));
        setReveal(created);
        const rows = await run((token) => fetchUserProjectApiKeys(token, projectId));
        setKeys(rows);
        setStatus("ready");
        return true;
      } catch (err) {
        const safe = safeErrorMessage(err);
        setError(safe.message);
        setErrorStatus(safe.status);
        return false;
      } finally {
        setCreating(false);
      }
    },
    [projectId, creating, run],
  );

  const revokeKey = useCallback(
    async (keyId: string): Promise<boolean> => {
      if (!projectId || revokingId) return false;
      setRevokingId(keyId);
      setError(null);
      setErrorStatus(null);
      try {
        await run((token) => revokeUserProjectApiKey(token, projectId, keyId));
        const rows = await run((token) => fetchUserProjectApiKeys(token, projectId));
        setKeys(rows);
        setStatus("ready");
        return true;
      } catch (err) {
        const safe = safeErrorMessage(err);
        setError(safe.message);
        setErrorStatus(safe.status);
        return false;
      } finally {
        setRevokingId(null);
      }
    },
    [projectId, revokingId, run],
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
