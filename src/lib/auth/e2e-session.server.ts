/**
 * Server-only E2E session bootstrap. Filename suffix keeps this out of the
 * client bundle (TanStack Start import protection).
 */

import { evaluateE2EServerAccess } from "./e2e-guards";

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

function readServerGuards() {
  return evaluateE2EServerAccess({
    nodeEnv: process.env.NODE_ENV,
    e2eTestMode: process.env.HELIOS_E2E_TEST_MODE,
    accessToken: process.env.HELIOS_E2E_ACCESS_TOKEN,
    jwksUrl: process.env.HELIOS_E2E_JWKS_URL ?? process.env.WORKOS_JWKS_URL,
    issuer: process.env.HELIOS_E2E_ISSUER ?? process.env.WORKOS_ISSUER,
  });
}

/** Server-only: build the E2E session or return null when disabled. */
export function getE2ESessionOrNull(): E2ESessionPayload | null {
  const gate = readServerGuards();
  if (!gate.ok) return null;
  const accessToken = (process.env.HELIOS_E2E_ACCESS_TOKEN ?? "").trim();
  const organizationId = (process.env.HELIOS_E2E_ORG_ID ?? "").trim();
  const userId = (process.env.HELIOS_E2E_USER_ID ?? "user_e2e").trim();
  if (!organizationId) return null;
  return {
    accessToken,
    organizationId,
    user: {
      id: userId,
      email: process.env.HELIOS_E2E_USER_EMAIL?.trim() || "e2e@helios.test",
      firstName: "E2E",
      lastName: "Tester",
    },
  };
}

export function e2eAccessDeniedReason(): string | null {
  const gate = readServerGuards();
  return gate.ok ? null : gate.reason;
}
