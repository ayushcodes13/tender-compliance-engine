import { expect, test } from "@playwright/test";

/**
 * The 401 copy must not send someone hunting for a login form. This pilot
 * resolves identity from deployment configuration, and #108 deliberately
 * removed the sign-in UI, so "Sign in again" would be advice pointing at
 * something that does not exist.
 */
test.describe("unauthorized copy", () => {
  test("does not tell the user to sign in again", async ({ page }) => {
    await page.route(
      (url) => url.pathname.replace(/^\/api\/backend/, "") === "/projects/project-1",
      async (route) => {
        if (route.request().resourceType() !== "fetch") return route.continue();
        return route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Not authenticated" }),
        });
      },
    );

    await page.goto("/projects/project-1");
    await expect(page.getByText(/did not recognize your access/i)).toBeVisible();
    await expect(page.getByText(/sign in again/i)).toHaveCount(0);
  });
});
