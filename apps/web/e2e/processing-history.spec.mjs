import { expect, test } from "@playwright/test";

const now = "2026-10-07T10:00:00Z";

test("failed tender shows safe stage history and preserves retry action", async ({ page }) => {
  await page.route("**/api/backend/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/backend/, "");
    const json = (body) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });

    if (path === "/projects/project-1") {
      return json({
        id: "project-1",
        organization_id: "org-1",
        name: "Pilot Tender",
        external_tender_id: null,
        status: "tender_uploaded",
        created_by: "user-1",
        created_at: now,
        updated_at: now,
      });
    }
    if (path === "/projects/project-1/documents") {
      return json([{
        document_id: "document-1",
        display_name: "tender.pdf",
        document_type: "tender",
        version_number: 1,
        sha256: "a".repeat(64),
        mime_type: "application/pdf",
        size_bytes: 1024,
        processing_status: "failed",
        parser_name: null,
        parser_version: null,
        ocr_name: null,
        ocr_version: null,
        created_at: now,
      }]);
    }
    if (path === "/projects/project-1/documents/document-1/versions/1/runs") {
      return json([{
        id: "run-1",
        run_id: "run-id-1",
        attempt: 5,
        stage: "extract",
        status: "failed",
        error_type: "ProviderError",
        error_message: "private provider response must not appear in the UI",
        started_at: now,
        completed_at: now,
      }]);
    }
    return json([]);
  });

  await page.goto("/projects/project-1");
  await expect(page.getByText("tender.pdf")).toBeVisible();
  await page.getByText("Processing history").click();
  await expect(page.getByText("Requirement extraction — failed (attempt 5)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry processing" })).toBeVisible();
  await expect(page.getByText("private provider response", { exact: false })).toHaveCount(0);
});
