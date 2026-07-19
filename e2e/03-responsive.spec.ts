import { expect, test, uniqueSlug } from "./fixtures/helios";
import { readFileSync } from "node:fs";

test.describe("narrow viewport smoke", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("onboarding and key reveal remain usable", async ({
    page,
    consoleGate,
    apiBase,
    humanToken,
  }) => {
    void consoleGate;
    const slug = uniqueSlug("mobile");
    // Create via API so this smoke does not depend on zero-project UI state.
    const created = await page.request.post(`${apiBase}/v2/user/projects`, {
      headers: {
        Authorization: `Bearer ${humanToken}`,
        "Content-Type": "application/json",
      },
      data: { name: `Mobile ${slug}`, slug },
    });
    expect(created.status()).toBe(201);
    const project = await created.json();

    await page.goto("/app/getting-started");
    await page.evaluate((id) => localStorage.setItem("helios.selectedProjectId", id), project.id);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Getting started" })).toBeVisible();

    await page.goto("/app/settings/api-keys");
    await page.getByLabel("Key name").fill("mobile-key");
    await page.getByRole("button", { name: "Create API key" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByLabel("New project API key")).toBeVisible();
    await dialog.getByRole("button", { name: "I have copied the key" }).click();
    await expect(dialog).toHaveCount(0);
  });
});
