/**
 * Client-side E2E token cache. Fetches from `/api/e2e/session` (server-gated).
 */

import { isE2EClientFlag } from "./e2e-guards";

export type E2ESessionPayload = {
  accessToken: string;
  organizationId: string;
  user: {
    id: string;
    email: string;
    firstName: string;
    lastName: string;
  };
};

let cachedToken: string | null = null;
let cachedOrgId: string | null = null;
let inflight: Promise<E2ESessionPayload> | null = null;

async function fetchE2ESession(): Promise<E2ESessionPayload> {
  if (!isE2EClientFlag()) {
    throw new Error("E2E session requested outside E2E client mode");
  }
  const response = await fetch("/api/e2e/session", {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`E2E session unavailable (${response.status})`);
  }
  return (await response.json()) as E2ESessionPayload;
}

export async function getE2EAccessToken(): Promise<string | null> {
  if (!isE2EClientFlag()) return null;
  if (cachedToken) return cachedToken;
  if (!inflight) {
    inflight = fetchE2ESession().finally(() => {
      inflight = null;
    });
  }
  const session = await inflight;
  cachedToken = session.accessToken;
  cachedOrgId = session.organizationId;
  return cachedToken;
}

export async function getE2EOrganizationId(): Promise<string | null> {
  if (!isE2EClientFlag()) return null;
  if (cachedOrgId) return cachedOrgId;
  await getE2EAccessToken();
  return cachedOrgId;
}

export function clearE2EClientCache(): void {
  cachedToken = null;
  cachedOrgId = null;
}
