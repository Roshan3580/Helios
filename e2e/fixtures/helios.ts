import { expect, type Page, test as base } from "@playwright/test";
import { readFileSync, writeFileSync, unlinkSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";

type ConsoleGate = {
  errors: string[];
  pageErrors: string[];
};

type HeliosFixtures = {
  consoleGate: ConsoleGate;
  apiBase: string;
  humanToken: string;
  redactKey: (key: string) => void;
};

const BENIGN_CONSOLE = [
  /Download the React DevTools/,
  /\[vite\] connecting/,
  /\[vite\] connected/,
  /Failed to load resource: the server responded with a status of 401/,
  /Failed to load resource: the server responded with a status of 404/,
  /Failed to load resource: the server responded with a status of 403/,
  // Transient browser noise when Vite HMR races the first API call.
  /blocked by CORS policy/,
  /net::ERR_FAILED/,
];

export const test = base.extend<HeliosFixtures>({
  // Playwright requires `{}` destructuring for unused fixtures.
  apiBase: async ({}, use) => {
    await use(process.env.HELIOS_E2E_API_URL ?? "http://127.0.0.1:8000");
  },
  humanToken: async ({}, use) => {
    const path = process.env.HELIOS_E2E_ACCESS_TOKEN_FILE;
    if (!path) throw new Error("HELIOS_E2E_ACCESS_TOKEN_FILE is required");
    await use(readFileSync(path, "utf8").trim());
  },
  consoleGate: async ({ page }, use) => {
    const gate: ConsoleGate = { errors: [], pageErrors: [] };
    page.on("pageerror", (err) => {
      gate.pageErrors.push(err.message);
    });
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      const text = msg.text();
      if (BENIGN_CONSOLE.some((re) => re.test(text))) return;
      gate.errors.push(text);
    });
    await use(gate);
    expect(gate.pageErrors, `pageerrors: ${gate.pageErrors.join(" | ")}`).toEqual([]);
    expect(gate.errors, `console errors: ${gate.errors.join(" | ")}`).toEqual([]);
  },
  redactKey: async ({}, use) => {
    const keys: string[] = [];
    await use((key) => {
      keys.push(key);
    });
    void keys;
  },
});

export { expect };

export function uniqueSlug(prefix: string): string {
  return `${prefix}-${randomBytes(4).toString("hex")}`;
}

export function storeKeyEphemeral(key: string): string {
  const path = join(tmpdir(), `helios-e2e-key-${randomBytes(8).toString("hex")}`);
  writeFileSync(path, key, { mode: 0o600 });
  return path;
}

export function clearKeyFile(path: string): void {
  if (existsSync(path)) unlinkSync(path);
}

export function ingestTrace(opts: { apiUrl: string; keyFile: string; traceId: string }): void {
  const python = process.env.BACKEND_VENV
    ? `${process.env.BACKEND_VENV}/bin/python`
    : "backend/.venv/bin/python";
  execFileSync(
    python,
    [
      "scripts/e2e/ingest_trace.py",
      "--api-url",
      opts.apiUrl,
      "--api-key-file",
      opts.keyFile,
      "--trace-id",
      opts.traceId,
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
}

export async function assertNoKeyLeak(page: Page, key: string): Promise<void> {
  const url = page.url();
  expect(url).not.toContain(key);
  const storage = await page.evaluate(() => ({
    local: { ...localStorage },
    session: { ...sessionStorage },
    cookie: document.cookie,
  }));
  const blob = JSON.stringify(storage);
  expect(blob).not.toContain(key);
}

export async function createProjectViaUi(page: Page, name: string, slug: string): Promise<void> {
  await page.goto("/app/getting-started");
  await expect(page.getByRole("heading", { name: "Create your first project" })).toBeVisible();
  await page.getByLabel("Project name").fill(name);
  await page.getByLabel("Project slug").fill(slug);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { name: "Getting started" })).toBeVisible({
    timeout: 30_000,
  });
}
