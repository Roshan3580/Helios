/**
 * E2E authentication seam guards.
 *
 * The browser may see only the boolean client flag `VITE_HELIOS_E2E_TEST_MODE`.
 * The access token itself is never a VITE_* value and is served only from a
 * server route that passes these guards.
 */

export type E2EGuardInput = {
  nodeEnv: string | undefined;
  e2eTestMode: string | undefined;
  accessToken: string | undefined;
  jwksUrl: string | undefined;
  issuer: string | undefined;
};

export type E2EGuardResult = { ok: true } | { ok: false; reason: string };

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

export function isLoopbackUrl(raw: string | undefined): boolean {
  if (!raw) return false;
  try {
    const url = new URL(raw);
    return LOOPBACK_HOSTS.has(url.hostname);
  } catch {
    return false;
  }
}

/**
 * Server-side gate for minting/serving the E2E access token.
 * Disabled by default; impossible to enable under NODE_ENV=production.
 */
export function evaluateE2EServerAccess(input: E2EGuardInput): E2EGuardResult {
  if ((input.nodeEnv ?? "").toLowerCase() === "production") {
    return { ok: false, reason: "e2e_auth_disabled_in_production" };
  }
  if (input.e2eTestMode !== "true") {
    return { ok: false, reason: "e2e_auth_flag_unset" };
  }
  if (!input.accessToken || !input.accessToken.trim()) {
    return { ok: false, reason: "e2e_access_token_missing" };
  }
  // Prefer an explicit loopback JWKS URL. If only issuer is set, it must also
  // be loopback so a production WorkOS issuer cannot be paired with E2E mode.
  if (input.jwksUrl) {
    if (!isLoopbackUrl(input.jwksUrl)) {
      return { ok: false, reason: "e2e_jwks_not_loopback" };
    }
  } else if (input.issuer && !isLoopbackUrl(input.issuer)) {
    return { ok: false, reason: "e2e_issuer_not_loopback" };
  } else if (!input.jwksUrl && !input.issuer) {
    return { ok: false, reason: "e2e_jwks_or_issuer_required" };
  }
  return { ok: true };
}

export function isE2EClientFlag(
  flag: string | undefined = import.meta.env.VITE_HELIOS_E2E_TEST_MODE,
): boolean {
  return flag === "true";
}
