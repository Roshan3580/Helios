import { readFileSync } from "node:fs";
import { expect, test, uniqueSlug } from "./fixtures/helios";

test("organization isolation across separate auth contexts", async ({
  page,
  browser,
  apiBase,
  humanToken,
  consoleGate,
}) => {
  void consoleGate;
  const orgBTokenPath = process.env.HELIOS_E2E_ORG_B_TOKEN_FILE;
  expect(orgBTokenPath).toBeTruthy();
  const orgBToken = readFileSync(orgBTokenPath!, "utf8").trim();

  // Create project in org B only — leave org A empty for the canonical suite.
  const slugB = uniqueSlug("iso-b");
  const createdB = await page.request.post(`${apiBase}/v2/user/projects`, {
    headers: {
      Authorization: `Bearer ${orgBToken}`,
      "Content-Type": "application/json",
    },
    data: { name: "Iso B", slug: slugB },
  });
  expect(createdB.status()).toBe(201);
  const projectB = await createdB.json();

  // Org A cannot list or access project B
  const listA = await page.request.get(`${apiBase}/v2/user/projects`, {
    headers: { Authorization: `Bearer ${humanToken}` },
  });
  expect(listA.status()).toBe(200);
  const projectsA = await listA.json();
  expect(projectsA.every((p: { id: string }) => p.id !== projectB.id)).toBeTruthy();

  const cross = await page.request.get(`${apiBase}/v2/user/projects/${projectB.id}/dashboard`, {
    headers: { Authorization: `Bearer ${humanToken}` },
  });
  expect(cross.status()).toBe(404);

  // Project API key cannot hit human management
  const keyRes = await page.request.post(`${apiBase}/v2/user/projects/${projectB.id}/api-keys`, {
    headers: {
      Authorization: `Bearer ${orgBToken}`,
      "Content-Type": "application/json",
    },
    data: { name: "iso-key", scopes: ["traces:read"] },
  });
  expect(keyRes.status()).toBe(201);
  const createdKey = await keyRes.json();
  const machineToken = createdKey.plaintext_key as string;
  const humanWithKey = await page.request.get(`${apiBase}/v2/user/projects`, {
    headers: { Authorization: `Bearer ${machineToken}` },
  });
  expect(humanWithKey.status()).toBe(401);

  // Separate browser request context for org B identity check
  const contextB = await browser.newContext();
  const pageB = await contextB.newPage();
  const sessionProbe = await pageB.request.get(`${apiBase}/v2/user/me`, {
    headers: { Authorization: `Bearer ${orgBToken}` },
  });
  expect(sessionProbe.status()).toBe(200);
  const meB = await sessionProbe.json();
  expect(meB.organization.workos_org_id).toBe(process.env.HELIOS_E2E_ORG_B);
  await contextB.close();
});
