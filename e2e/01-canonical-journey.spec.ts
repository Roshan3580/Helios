import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { randomBytes } from "node:crypto";

import {
  assertNoKeyLeak,
  clearKeyFile,
  createProjectViaUi,
  expect,
  ingestTrace,
  storeKeyEphemeral,
  test,
  uniqueSlug,
} from "./fixtures/helios";

/**
 * Canonical authenticated journey: zero projects → create → key → ingest →
 * analyze → insights → revoke. Serial by design (one shared org state).
 */
test.describe.configure({ mode: "serial" });

test.describe("canonical release gate", () => {
  const slug = uniqueSlug("e2e-proj");
  const projectName = `E2E ${slug}`;
  let plaintextKey = "";
  let keyFile = "";
  let traceId = "";
  let projectId = "";

  test("zero-project states and project creation", async ({ page, consoleGate }) => {
    void consoleGate;
    await page.goto("/app/dashboard");
    await expect(page.getByRole("main").getByText("No project selected")).toBeVisible();
    await expect(page.getByRole("main").getByRole("link", { name: "Getting started" })).toBeVisible();
    await expect(page.getByText(/acme/i)).toHaveCount(0);

    await page.goto("/app/traces");
    await expect(page.getByRole("main").getByText("No project selected")).toBeVisible();
    await expect(page.getByRole("main").getByRole("link", { name: "Getting started" })).toBeVisible();

    await page.goto("/app/insights");
    await expect(page.getByRole("main").getByText("No project selected")).toBeVisible();
    await expect(page.getByRole("main").getByRole("link", { name: "Getting started" })).toBeVisible();

    await createProjectViaUi(page, projectName, slug);
    await expect(page.getByLabel("Project")).toContainText(projectName);

    projectId = await page.evaluate(() => localStorage.getItem("helios.selectedProjectId"));
    expect(projectId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );

    await page.reload();
    await expect(page.getByLabel("Project")).toContainText(projectName);

    // Duplicate slug → safe error
    await page.goto("/app/getting-started");
    // Already have a project — form is on zero-project only. Exercise via API.
    const token = readFileSync(process.env.HELIOS_E2E_ACCESS_TOKEN_FILE!, "utf8").trim();
    const dup = await page.request.post(`${process.env.HELIOS_E2E_API_URL}/v2/user/projects`, {
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      data: { name: "Dup", slug },
    });
    expect(dup.status()).toBe(409);
    const detail = (await dup.json()).detail as string;
    expect(detail.toLowerCase()).toContain("already exists");
    expect(detail.toLowerCase()).not.toContain("uq_");
  });

  test("one-time API key lifecycle", async ({ page, consoleGate, apiBase }) => {
    void consoleGate;
    void apiBase;
    await page.goto("/app/settings/api-keys");
    await expect(page.getByRole("heading", { name: "Project API keys" })).toBeVisible();

    await page.getByLabel("Key name").fill("e2e-release-key");
    // scopes default to both ingest+read
    await page.getByRole("button", { name: "Create API key" }).click();

    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("heading", { name: "Copy this key now. Helios will not show it again." }),
    ).toBeVisible();
    const keyEl = dialog.getByLabel("New project API key");
    plaintextKey = (await keyEl.innerText()).trim();
    expect(plaintextKey).toMatch(/^hel_proj_[A-Za-z0-9]+_[A-Za-z0-9+/=_-]+$/);

    // Grant clipboard permissions and copy via explicit click.
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    await dialog.getByRole("button", { name: "Copy project API key" }).click();
    await expect(dialog.getByRole("button", { name: "Copied" })).toBeVisible();

    await assertNoKeyLeak(page, plaintextKey);
    const attrs = await keyEl.evaluate((node) =>
      Array.from(node.attributes)
        .map((a) => `${a.name}=${a.value}`)
        .join(" "),
    );
    expect(attrs).not.toContain(plaintextKey);

    keyFile = storeKeyEphemeral(plaintextKey);

    await dialog.getByRole("button", { name: "I have copied the key" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByLabel("New project API key")).toHaveCount(0);

    await page.reload();
    await expect(page.getByText("e2e-release-key")).toBeVisible();
    await expect(page.getByText(plaintextKey)).toHaveCount(0);
    await expect(page.getByText(/key_hash/i)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Revoke" })).toBeVisible();
  });

  test("telemetry ingestion, traces, analysis, dashboard", async ({
    page,
    consoleGate,
    apiBase,
  }) => {
    void consoleGate;
    expect(keyFile).toBeTruthy();
    traceId = randomBytes(16).toString("hex");
    ingestTrace({ apiUrl: apiBase, keyFile, traceId });

    await page.goto("/app/getting-started");

    // All three setup paths render, and the Node instructions are truthful
    // about publication status (repository artifact install, no fake npm name).
    await expect(page.getByRole("heading", { name: "Python SDK" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Node.js / TypeScript SDK" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Raw OTLP HTTP" })).toBeVisible();
    await expect(page.getByText(/not yet published/i)).toBeVisible();
    await expect(page.getByText("Helios.configure({")).toBeVisible();
    await expect(page.getByText("helios-ai-sdk-0.1.0.tgz")).toBeVisible();

    await page.getByRole("button", { name: "Check for traces" }).click();
    await expect(page.getByText(/Telemetry received/i)).toBeVisible({ timeout: 30_000 });
    await page.getByRole("link", { name: "Open trace", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/app/traces/${traceId}`));
    await expect(page.getByRole("listbox", { name: "Trace timeline" })).toBeVisible();
    await expect(page.getByText("tool.lookup")).toBeVisible();

    await page.getByRole("button", { name: "Analyze trace" }).click();
    await expect(page.getByText("single-trace-v1")).toBeVisible({ timeout: 30_000 });
    const findings = page.getByLabel("Findings");
    await expect(findings).toBeVisible();
    // Limitations may honestly mention unavailable cost/RAG analysis; findings must not.
    await expect(findings.getByText(/cost|hallucination|RAG citation|evaluation/i)).toHaveCount(0);

    const findingButton = page.getByRole("button", { name: /View span/ }).first();
    if (await findingButton.count()) {
      await findingButton.click();
      await expect(
        page.getByRole("listbox", { name: "Trace timeline" }).getByRole("option", { selected: true }),
      ).toBeVisible();
    }

    // Narrative disabled (no provider)
    const generate = page.getByRole("button", { name: "Generate explanation" });
    if (await generate.count()) {
      await generate.click();
    }
    await expect(
      page.getByText("Narrative explanation is not enabled for this Helios environment."),
    ).toBeVisible({ timeout: 15_000 });

    await page.goto("/app/dashboard");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByText(/\bacme\b/i)).toHaveCount(0);
    await expect(page.getByText(/using demo data|demo project selected/i)).toHaveCount(0);
    // Positive signal: real telemetry counts should be non-empty after ingest.
    await expect(page.getByText(/Traces|Error rate|Spans/i).first()).toBeVisible();
  });

  test("project insights with seeded windows", async ({
    page,
    consoleGate,
    apiBase,
    humanToken,
  }) => {
    void consoleGate;
    expect(projectId).toBeTruthy();
    const seed = await page.request.post(`${apiBase}/v2/e2e/seed-insights`, {
      headers: {
        Authorization: `Bearer ${humanToken}`,
        "Content-Type": "application/json",
      },
      data: { project_id: projectId, hours: 24 },
    });
    expect(seed.status()).toBe(201);

    await page.goto("/app/insights");
    await page.getByLabel("Time window").selectOption("24");
    await page.getByRole("button", { name: "Analyze project" }).click();
    await expect(page.getByText("project-window-v1")).toBeVisible({ timeout: 45_000 });
    const projectFindings = page.getByLabel("Project findings");
    await expect(projectFindings).toBeVisible();
    await expect(
      projectFindings.getByText(/hallucination|RAG citation|evaluation claim/i),
    ).toHaveCount(0);

    const gen = page.getByRole("button", { name: "Generate explanation" });
    if (await gen.count()) await gen.click();
    await expect(
      page.getByText("Narrative explanation is not enabled for this Helios environment."),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("revoke key and block machine auth", async ({ page, consoleGate, apiBase }) => {
    void consoleGate;
    await page.goto("/app/settings/api-keys");
    await page.getByRole("button", { name: "Revoke" }).first().click();
    const confirm = page.getByRole("alertdialog");
    await expect(confirm.getByRole("heading", { name: "Revoke this API key?" })).toBeVisible();
    await expect(confirm.getByText(/e2e-release-key/)).toBeVisible();
    await confirm.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("button", { name: "Revoke" }).first()).toBeVisible();

    await page.getByRole("button", { name: "Revoke" }).first().click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Revoke key" }).click();
    await expect(page.getByText(/revoked/i).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(plaintextKey)).toHaveCount(0);

    const read = await page.request.get(`${apiBase}/v2/traces`, {
      headers: { Authorization: `Bearer ${plaintextKey}` },
    });
    expect([401, 403]).toContain(read.status());

    // OTLP with revoked key
    const failPath = join(tmpdir(), `helios-revoked-${randomBytes(4).toString("hex")}`);
    writeFileSync(failPath, plaintextKey, { mode: 0o600 });
    let ingestFailed = false;
    try {
      ingestTrace({
        apiUrl: apiBase,
        keyFile: failPath,
        traceId: randomBytes(16).toString("hex"),
      });
    } catch {
      ingestFailed = true;
    }
    clearKeyFile(failPath);
    expect(ingestFailed).toBeTruthy();

    clearKeyFile(keyFile);
  });
});
