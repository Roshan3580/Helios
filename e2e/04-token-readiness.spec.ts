import { expect, test } from "./fixtures/helios";

/**
 * Checkpoint 27 browser gate: the access token is not ready at the moment the
 * authenticated shell mounts, and the UI must treat that as ordinary loading
 * rather than an expired session.
 *
 * The E2E seam models this without weakening any security control: the user and
 * the access token are two separate round trips to the server-gated
 * `/api/e2e/session` route, so there is a real window in which a valid user
 * exists while the token is still being fetched. Delaying that route widens the
 * window deterministically — no security guard is bypassed, no token is supplied
 * by the browser, and no header value is read or logged.
 *
 * Before this fix the shell reported "Your session has expired" during exactly
 * this window, without ever contacting the backend.
 *
 * Assertions here are deliberately independent of how many projects the shared
 * E2E organization happens to contain, since earlier specs create projects in it.
 */
test.describe("access-token readiness", () => {
  test("delayed token initialization never renders session expiry", async ({
    page,
    consoleGate,
  }) => {
    void consoleGate;

    const apiRequests: { path: string; authorized: boolean }[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (!url.pathname.startsWith("/v2/")) return;
      apiRequests.push({
        path: url.pathname,
        // Presence only — the header value is never read, recorded, or logged.
        authorized: Boolean(request.headers()["authorization"]),
      });
    });

    // Widen the "user exists, token still initializing" window.
    await page.route("**/api/e2e/session", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 700));
      await route.fallback();
    });

    await page.goto("/app/dashboard");

    // We are inside the initialization window: an ordinary bounded loading state.
    await expect(page.getByText("Loading projects…")).toBeVisible();
    // No expiry panel, and critically no authenticated request at all yet.
    await expect(page.getByRole("main").getByText("Your session has expired")).toHaveCount(0);
    expect(apiRequests).toEqual([]);

    // Readiness is reached and the project read completes.
    await expect(page.getByText("Loading projects…")).toHaveCount(0, { timeout: 15_000 });

    // The expiry panel must never have appeared at any point.
    await expect(page.getByRole("main").getByText("Your session has expired")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Sign in again" })).toHaveCount(0);

    // Every authenticated request that was issued carried a token, and the
    // profile and project reads each happened exactly once — no request storm.
    expect(apiRequests.length).toBeGreaterThan(0);
    for (const request of apiRequests) {
      expect(request.authorized, `unauthenticated request to ${request.path}`).toBe(true);
    }
    expect(apiRequests.filter((r) => r.path === "/v2/user/me")).toHaveLength(1);
    expect(apiRequests.filter((r) => r.path === "/v2/user/projects")).toHaveLength(1);
  });

  test("a reload re-establishes readiness without an expiry panel", async ({
    page,
    consoleGate,
  }) => {
    void consoleGate;
    await page.goto("/app/dashboard");
    await expect(page.getByText("Loading projects…")).toHaveCount(0);

    await page.reload();
    await expect(page.getByText("Loading projects…")).toHaveCount(0);
    await expect(page.getByRole("main").getByText("Your session has expired")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Sign in again" })).toHaveCount(0);
  });
});
