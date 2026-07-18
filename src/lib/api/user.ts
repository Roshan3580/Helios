/**
 * Human-authenticated (WorkOS JWT) API client for /v2/user routes.
 *
 * Deliberately separate from the legacy public apiFetch client: user JWTs are
 * attached ONLY here, never to legacy/demo requests. The token is passed in by
 * the caller (obtained fresh via useAccessToken().getAccessToken() immediately
 * before the call) and is never persisted to localStorage/sessionStorage or
 * logged.
 */

import { API_BASE_URL } from "./client";

export interface UserOrganization {
  id: string | null;
  workos_org_id: string | null;
  slug: string | null;
  name: string | null;
  linked: boolean;
}

export interface UserMe {
  user_id: string;
  workos_user_id: string;
  organization: UserOrganization;
  role: string | null;
  permissions: string[];
}

export interface UserProject {
  id: string;
  slug: string;
  name: string;
  environment: string;
}

export class UserApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "UserApiError";
  }
}

async function userApiFetch<T>(path: string, accessToken: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!response.ok) {
    // Do not include response bodies that might echo request details.
    throw new UserApiError(`Request failed (${response.status})`, response.status);
  }
  return (await response.json()) as T;
}

export function fetchUserMe(accessToken: string): Promise<UserMe> {
  return userApiFetch<UserMe>("/v2/user/me", accessToken);
}

export function fetchUserProjects(accessToken: string): Promise<UserProject[]> {
  return userApiFetch<UserProject[]>("/v2/user/projects", accessToken);
}
