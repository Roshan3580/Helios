/** Shared test utilities: env isolation and runtime reset between tests. */

import { _resetForTests } from "../../src/runtime.js";

export const TEST_API_KEY = "hel_proj_0123456789abcdef_testsecrettestsecrettest";

const HELIOS_ENV_VARS = [
  "HELIOS_API_KEY",
  "HELIOS_ENDPOINT",
  "HELIOS_SERVICE_NAME",
  "HELIOS_SERVICE_VERSION",
  "HELIOS_ENVIRONMENT",
  "HELIOS_CAPTURE_CONTENT",
  "OTEL_SERVICE_NAME",
  "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
];

export function clearHeliosEnv(): void {
  for (const name of HELIOS_ENV_VARS) {
    delete process.env[name];
  }
}

export async function resetRuntime(): Promise<void> {
  await _resetForTests();
  clearHeliosEnv();
}
