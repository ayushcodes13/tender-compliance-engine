import { expect, test } from "@playwright/test";

const createdAt = "2026-10-04T12:00:00Z";

function project(status = "draft") {
  return {
    id: "project-1",
    organization_id: "org-1",
    name: "Pilot Tender",
    external_tender_id: null,
    status,
    created_by: "user-1",
    created_at: createdAt,
    updated_at: createdAt,
  };
}

function tenderDocument() {
  return {
    document_id: "tender-doc-1",
    display_name: "tender.pdf",
    document_type: "tender",
    version_number: 1,
    sha256: "a".repeat(64),
    mime_type: "application/pdf",
    size_bytes: 42,
    processing_status: "parsed",
    parser_name: "pypdf",
    parser_version: "test",
    ocr_name: null,
    ocr_version: null,
    created_at: createdAt,
  };
}

function oemDocument() {
  return {
    document_id: "oem-doc-1",
    display_name: "vendor-compliance.pdf",
    document_type: "compliance_sheet",
    vendor_name: "Acme Instruments",
    product_name: "Model X",
    product_sku: null,
    version_number: 1,
    sha256: "b".repeat(64),
    mime_type: "application/pdf",
    size_bytes: 55,
    processing_status: "parsed",
    parser_name: "pypdf",
    parser_version: "test",
    ocr_name: null,
    ocr_version: null,
    created_at: createdAt,
  };
}

function finalMatrixRow() {
  return {
    serial: 1,
    requirement_id: "req-1",
    tender_requirement: "Positioning resolution shall be 1 µm or better.",
    category: "Motion",
    clause: "4.2",
    source_page: 12,
    mandatory: true,
    user_notes: null,
    review_status: "reviewed",
    normalized_text: "Positioning resolution <= 1 µm",
    raw_source: "Positioning resolution shall be 1 µm or better.",
    uncertainty: "low",
    ocr_warning: false,
    evidence_id: "evidence-1",
    evidence_score: 0.97,
    evidence_oem_document: "vendor-compliance.pdf",
    evidence_oem_version: 1,
    vendor_spec_parameter: "positioning resolution",
    vendor_spec_value: 1,
    vendor_spec_unit: "µm",
    vendor_spec_lower_bound: null,
    vendor_spec_upper_bound: null,
    vendor_spec_source_text: "Positioning resolution: 1 µm",
    vendor_spec_source_page: 3,
    vendor_spec_extraction_method: "deterministic",
    vendor_spec_issues: [],
    assessment_status: "compliant",
    assessment_suggested_status: "compliant",
    assessment_reason_code: "numeric_requirement_satisfied",
    assessment_reason_text: "1 µm satisfies the tender maximum of 1 µm.",
    assessment_is_confirmed: true,
    assessment_reviewer_id: "user-1",
    assessment_reviewed_at: createdAt,
    assessment_version: 1,
    has_unresolved_conflict: false,
    clarification_statuses: [],
    deviation_statuses: [],
  };
}

test("buyer can create a project, upload tender/OEM sources, and reach the compliance sheet", async ({ page }) => {
  let currentProject = project();
  let tenderDocs = [];
  let oemDocs = [];

  await page.route("**/api/backend/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/backend/, "");
    const method = request.method();

    const json = (body, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    if (path === "/projects" && method === "GET") {
      return json([]);
    }
    if (path === "/projects" && method === "POST") {
      return json(currentProject, 201);
    }
    if (path === "/projects/project-1" && method === "GET") {
      return json(currentProject);
    }
    if (path === "/projects/project-1/documents" && method === "GET") {
      return json(tenderDocs);
    }
    if (path === "/projects/project-1/oem-documents" && method === "GET") {
      return json(oemDocs);
    }
    if (path === "/projects/project-1/upload" && method === "POST") {
      currentProject = project("tender_uploaded");
      const doc = tenderDocument();
      tenderDocs = [doc];
      return json(
        {
          ...doc,
          stored_object_id: "stored-tender-1",
          storage_key: "org-1/project-1/tender-doc-1/v1/tender.pdf",
          filename: "tender.pdf",
          content_type: "application/pdf",
          content_length: 42,
          checksum_sha256: doc.sha256,
          project_status: "tender_uploaded",
          uploaded_at: createdAt,
        },
        201
      );
    }
    if (path === "/projects/project-1/oem-documents/upload" && method === "POST") {
      const doc = oemDocument();
      oemDocs = [doc];
      return json(
        {
          stored_object_id: "stored-oem-1",
          document_id: doc.document_id,
          version_number: doc.version_number,
          storage_key: "org-1/project-1/oem-doc-1/v1/vendor-compliance.pdf",
          filename: doc.display_name,
          content_type: doc.mime_type,
          content_length: doc.size_bytes,
          checksum_sha256: doc.sha256,
          processing_status: "uploaded",
          uploaded_at: createdAt,
        },
        201
      );
    }
    if (
      path ===
        "/projects/project-1/documents/tender-doc-1/versions/1/final-matrix" &&
      method === "GET"
    ) {
      return json([finalMatrixRow()]);
    }
    if (path === "/projects/project-1/submissions/" && method === "GET") {
      return json([]);
    }

    return json({ detail: `Unhandled browser smoke route: ${method} ${path}` }, 404);
  });

  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      name: /From Tender Documents to a Source-Linked Compliance Sheet/,
    })
  ).toBeVisible();
  await expect(page.getByText("PDF / DOCX in · XLSX / DOCX / PDF out")).toBeVisible();

  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Create tender project" }).click();
  await page.getByPlaceholder("Project name").fill("Pilot Tender");
  await page.getByRole("button", { name: "Create", exact: true }).click();

  await expect(page).toHaveURL(/\/projects\/project-1$/);
  await expect(page.getByRole("heading", { name: "Pilot Tender" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tender documents" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Vendor / OEM sources" })).toBeVisible();

  await page.getByLabel("Choose PDF or DOCX file").setInputFiles({
    name: "tender.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n% browser smoke fixture"),
  });

  await expect(page.getByText("tender.pdf", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Review requirements" }).first()
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Compliance sheet" }).first()
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Step 2 Vendor \/ OEM/ })
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Step 3 Review/ })
  ).toBeVisible();

  await page.getByLabel("Document type").selectOption("compliance_sheet");
  await page.getByRole("textbox", { name: "Vendor", exact: true }).fill("Acme Instruments");
  await page.getByRole("textbox", { name: "Product / model", exact: true }).fill("Model X");
  await page.locator("#vendor-sources input[type=file]").setInputFiles({
    name: "vendor-compliance.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n% vendor browser smoke fixture"),
  });

  await expect(
    page.getByText(/Uploaded vendor-compliance\.pdf as OEM source v1/)
  ).toBeVisible();
  await expect(page.getByText("Vendor compliance sheet").first()).toBeVisible();

  await page.getByRole("link", { name: "Compliance sheet" }).first().click();

  await expect(page).toHaveURL(/\/projects\/project-1\/matrix$/);
  await expect(
    page.getByRole("heading", { name: "Compliance sheet — Pilot Tender" })
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Final compliance sheet" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Step 4 Compliance sheet/ })
  ).toHaveAttribute("aria-current", "step");
  const summary = page.getByLabel("Compliance sheet summary");
  await expect(summary.getByText("Total requirements")).toBeVisible();
  await expect(summary.getByText("Compliant", { exact: true })).toBeVisible();
  await expect(summary.getByText("Needs attention")).toBeVisible();
  await expect(page.getByText("Positioning resolution shall be 1 µm or better.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Export XLSX" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export DOCX" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export PDF" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create draft submission" })).toBeVisible();
});
