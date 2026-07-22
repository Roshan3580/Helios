/**
 * Typed SDK errors. Error messages never include API keys, Authorization
 * headers, or exporter payloads.
 */

/** Invalid or conflicting configuration supplied by the caller/environment. */
export class HeliosConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HeliosConfigurationError";
  }
}

/** Optional instrumentation could not be loaded or registered. */
export class HeliosInstrumentationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HeliosInstrumentationError";
  }
}
