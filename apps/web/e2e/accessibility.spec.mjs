import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const WCAG_A_AA = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

const createdAt = "2026-10-05T12:00:00Z";

function seedProject() {
  return {
    id: "project-1",
    organization_id: "org-1",
    name: "Pilot Tender",
    external_tender_id: null,
    status: "draft",
    created_by: "user-1",
    created_at: createdAt,
    updated_at: createdAt,
  };
}

async function mockProjects(page, projects) {
  // Match the path, not the origin. `NEXT_PUBLIC_API_URL` is inlined at build
  // time, so the same spec has to work against both the relative fallback
  // (`/api/backend`, which is what CI builds) and an absolute development URL
  // such as `http://localhost:8000`.
  await page.route("**/projects", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(
      /^\/api\/backend/,
      "",
    );
    if (path === "/projects") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(projects),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}

/**
 * Settle the page before auditing it.
 *
 * The landing sections animate in with framer-motion, which drives inline
 * `opacity`. Measuring mid-animation makes every colour blend toward the
 * background and axe reports contrast failures that a user never sees — the
 * first draft of this spec failed on exactly that.
 *
 * Forcing the animated elements to their resting opacity means the whole page
 * is audited in its settled state, deterministically, including the below-fold
 * `whileInView` sections that would otherwise sit at opacity 0 and be skipped.
 */
async function settle(page) {
  await page.addStyleTag({
    content: "[style*='opacity'] { opacity: 1 !important; }",
  });
}

/**
 * Fails with a readable, actionable message instead of dumping raw axe JSON.
 * Serious/critical only: minor advisory findings on pages still being built
 * should not block a pilot release, but anything that makes the app unusable
 * with a keyboard or a screen reader should.
 */
async function expectNoSeriousViolations(page, label) {
  const results = await new AxeBuilder({ page }).withTags(WCAG_A_AA).analyze();

  const blocking = results.violations.filter(
    (violation) =>
      violation.impact === "serious" || violation.impact === "critical",
  );

  const summary = blocking
    .map((violation) => {
      const nodes = violation.nodes
        .slice(0, 5)
        .map((node) => {
          const data = node.any[0]?.data ?? node.all[0]?.data ?? {};
          const ratio = data.contrastRatio
            ? ` (${data.fgColor} on ${data.bgColor} = ${data.contrastRatio}, needs ${data.expectedContrastRatio})`
            : "";
          return `      ${node.target.join(" ")}${ratio}`;
        })
        .join("\n");
      return `  - [${violation.impact}] ${violation.id}: ${violation.help}\n${nodes}`;
    })
    .join("\n");

  expect(
    blocking,
    `Accessibility violations on ${label}:\n${summary || "(none)"}`,
  ).toEqual([]);
}

test.describe("accessibility", () => {
  test("landing page has no serious WCAG A/AA violations", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await settle(page);
    await expectNoSeriousViolations(page, "/");
  });

  test("contact page has no serious WCAG A/AA violations", async ({ page }) => {
    await page.goto("/contact");
    await settle(page);
    await expectNoSeriousViolations(page, "/contact");
  });

  test("access page has no serious WCAG A/AA violations", async ({ page }) => {
    await page.goto("/access");
    await settle(page);
    await expectNoSeriousViolations(page, "/access");
  });

  test("projects dashboard has no serious WCAG A/AA violations", async ({
    page,
  }) => {
    await mockProjects(page, [seedProject()]);
    await page.goto("/dashboard");
    // `exact` matters here: without it this also matches the "Active projects"
    // group heading, because role names match on substrings.
    await expect(
      page.getByRole("heading", { name: "Projects", exact: true }),
    ).toBeVisible();
    // Wait for real content, not just the shell, so the audit never runs
    // against a half-rendered dashboard.
    await expect(page.getByText("Pilot Tender")).toBeVisible();
    await settle(page);
    await expectNoSeriousViolations(page, "/dashboard");
  });

  test("empty dashboard state has no serious WCAG A/AA violations", async ({
    page,
  }) => {
    await mockProjects(page, []);
    await page.goto("/dashboard");
    await expect(
      page.getByRole("button", { name: "Create tender project" }),
    ).toBeVisible();
    await settle(page);
    await expectNoSeriousViolations(page, "/dashboard (empty state)");
  });

  test("create-project dialog has no serious WCAG A/AA violations", async ({
    page,
  }) => {
    await mockProjects(page, [seedProject()]);
    await page.goto("/dashboard");
    await page.getByRole("button", { name: "New tender" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await settle(page);
    await expectNoSeriousViolations(page, "/dashboard (create dialog open)");
  });
});

/**
 * Keyboard containment for the create-project modal. These are behavioural
 * rather than axe rules, so they are asserted directly: a modal that leaks
 * focus is unusable with a keyboard and axe does not report it.
 */
test.describe("create-project dialog keyboard behavior", () => {
  const focusInsideDialog = (page) =>
    page.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]')));

  test.beforeEach(async ({ page }) => {
    await mockProjects(page, [seedProject()]);
    await page.goto("/dashboard");
    await expect(
      page.getByRole("heading", { name: "Projects", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Pilot Tender")).toBeVisible();
  });

  test("moves focus into the dialog on open", async ({ page }) => {
    await page.getByRole("button", { name: "New tender" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(await focusInsideDialog(page)).toBe(true);
  });

  test("traps Tab inside the dialog", async ({ page }) => {
    await page.getByRole("button", { name: "New tender" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    for (let i = 0; i < 14; i += 1) {
      await page.keyboard.press("Tab");
      expect(
        await focusInsideDialog(page),
        `focus left the dialog after ${i + 1} Tab presses`,
      ).toBe(true);
    }
  });

  test("traps Shift+Tab inside the dialog", async ({ page }) => {
    await page.getByRole("button", { name: "New tender" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    for (let i = 0; i < 14; i += 1) {
      await page.keyboard.press("Shift+Tab");
      expect(
        await focusInsideDialog(page),
        `focus left the dialog after ${i + 1} Shift+Tab presses`,
      ).toBe(true);
    }
  });

  test("Escape closes the dialog and restores focus to the trigger", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "New tender" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "New tender" })).toBeFocused();
  });

  test("cancel returns focus to the trigger", async ({ page }) => {
    await page.getByRole("button", { name: "New tender" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    await page.getByRole("button", { name: "Cancel" }).click();

    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "New tender" })).toBeFocused();
  });
});
