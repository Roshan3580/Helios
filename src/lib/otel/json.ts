import type { OtelJsonValue } from "@/lib/api/user";

/** Stable key order for objects; arrays keep insertion order. */
export function sortJsonKeys(value: OtelJsonValue): OtelJsonValue {
  if (Array.isArray(value)) {
    return value.map((item) => sortJsonKeys(item as OtelJsonValue));
  }
  if (value && typeof value === "object") {
    const sorted: Record<string, OtelJsonValue> = {};
    for (const key of Object.keys(value).sort()) {
      sorted[key] = sortJsonKeys(value[key] as OtelJsonValue);
    }
    return sorted;
  }
  return value;
}

export function formatJsonValue(value: OtelJsonValue, space = 2): string {
  return JSON.stringify(sortJsonKeys(value), null, space);
}

export function isEmptyRecord(value: Record<string, unknown> | null | undefined): boolean {
  return !value || Object.keys(value).length === 0;
}

export function isEmptyList(value: unknown[] | null | undefined): boolean {
  return !value || value.length === 0;
}
