import { describe, expect, test } from "bun:test";

const routeSource = await Bun.file(
  new URL("../../routes/app.getting-started.tsx", import.meta.url),
).text();

describe("production onboarding export snippets", () => {
  test("Python distinguishes local completion from a failed flush", () => {
    expect(routeSource).toContain("flush_completed = helios.force_flush()");
    expect(routeSource).toContain("if not flush_completed:");
    expect(routeSource).toContain("Export did not complete locally");
  });

  test("TypeScript enables redacted diagnostics", () => {
    expect(routeSource).toContain('diagnostics: "warn"');
  });

  test("both snippets use neutral wording instead of false success", () => {
    expect(routeSource.match(/Export completed locally/g)?.length).toBe(2);
    expect(routeSource).toContain("Check Helios to confirm trace arrival");
    expect(routeSource).toContain("exporter errors are authoritative");
    expect(routeSource).not.toMatch(/trace (?:exported|submitted|sent)/i);
    expect(routeSource).not.toMatch(/export (?:succeeded|successful)/i);
  });
});
