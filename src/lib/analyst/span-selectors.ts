/**
 * Centralized, defensive parsing of backend span UI selectors.
 *
 * The engine emits selectors of the form `span:<span_id>`. The UI never
 * string-splits these ad hoc; everything flows through this helper and is
 * validated against the actually loaded trace before any navigation.
 */

const SPAN_SELECTOR_PREFIX = "span:";

/** Extract the span ID from a `span:<id>` selector, or null if malformed. */
export function parseSpanSelector(selector: string): string | null {
  if (!selector.startsWith(SPAN_SELECTOR_PREFIX)) return null;
  const spanId = selector.slice(SPAN_SELECTOR_PREFIX.length).trim();
  return spanId.length > 0 ? spanId : null;
}

/**
 * Resolve a finding's cited span IDs against the spans that are actually in
 * the loaded trace. Invalid or unknown IDs are dropped defensively; order is
 * preserved from the finding.
 */
export function resolveCitedSpanIds(
  citedSpanIds: string[],
  knownSpanIds: ReadonlySet<string>,
): string[] {
  return citedSpanIds.filter((spanId) => knownSpanIds.has(spanId));
}
