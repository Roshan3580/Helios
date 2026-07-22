/**
 * Frontend staging deployment contract guards (server-oriented helpers).
 * Never accept or embed access tokens here.
 */

export type StagingGuardInput = {
  nodeEnv?: string;
  heliosEnvironment?: string;
  e2eTestMode?: string;
  e2eAccessToken?: string;
  viteE2eTestMode?: string;
  apiBaseUrl?: string;
  workosRedirectUri?: string;
  workosCookiePassword?: string;
  frontendOrigin?: string;
};

export type StagingGuardResult = { ok: true } | { ok: false; reasons: string[] };

function isHttps(url: string): boolean {
  try {
    return new URL(url).protocol === "https:";
  } catch {
    return false;
  }
}

export function evaluateStagingFrontendContract(input: StagingGuardInput): StagingGuardResult {
  const env = (input.heliosEnvironment ?? "").toLowerCase();
  if (env !== "staging" && env !== "production") {
    return { ok: true };
  }

  const reasons: string[] = [];

  if (input.e2eTestMode === "true" || input.viteE2eTestMode === "true") {
    reasons.push("e2e_mode_forbidden_in_staging");
  }
  if (input.e2eAccessToken && input.e2eAccessToken.trim()) {
    reasons.push("e2e_access_token_forbidden_in_staging");
  }
  if (!input.apiBaseUrl || !isHttps(input.apiBaseUrl)) {
    reasons.push("api_base_url_must_be_https");
  }
  if (!input.workosRedirectUri || !isHttps(input.workosRedirectUri)) {
    reasons.push("workos_redirect_uri_must_be_https");
  }
  if (input.frontendOrigin && input.workosRedirectUri) {
    try {
      const origin = new URL(input.frontendOrigin).origin;
      const redirect = new URL(input.workosRedirectUri);
      if (redirect.origin !== origin) {
        reasons.push("workos_redirect_uri_must_match_frontend_origin");
      }
      if (!redirect.pathname.endsWith("/api/auth/callback")) {
        reasons.push("workos_redirect_uri_must_use_callback_path");
      }
    } catch {
      reasons.push("workos_redirect_uri_invalid");
    }
  }
  const password = input.workosCookiePassword ?? "";
  if (password.length < 32) {
    reasons.push("workos_cookie_password_too_short");
  }

  return reasons.length ? { ok: false, reasons } : { ok: true };
}
