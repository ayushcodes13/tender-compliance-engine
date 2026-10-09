import { expect, test } from "@playwright/test";

const createdAt = "2026-10-04T12:00:00Z";
const tenderDocumentId = "00000000-0000-4000-8000-000000000010";
const requirementId = "00000000-0000-4000-8000-000000000001";
const otherRequirementId = "00000000-0000-4000-8000-000000000002";
const firstSourceId = "00000000-0000-4000-8000-000000000101";
const secondSourceId = "00000000-0000-4000-8000-000000000102";
const thirdSourceId = "00000000-0000-4000-8000-000000000103";
const secondSourceQuote = "The equipment shall include a local emergency stop.";
const thirdSourceQuote = "The control panel shall display active fault codes.";
const coverageQuote = "The instrument shall include installation and operator training.";

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
    document_id: tenderDocumentId,
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
    requirement_id: requirementId,
    tender_requirement: "Positioning resolution shall be 1 µm or better.",
    category: "Motion",
    clause: "4.2",
    source_page: 12,
    source_anchor_id: firstSourceId,
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
  let exportArtifacts = [];

  await page.route(
    (url) => {
      // Strip the proxy prefix so this matches both the relative fallback and
      // an absolute API origin.
      const path = url.pathname.replace(/^\/api\/backend/, "");
      return path === "/projects" || path.startsWith("/projects/");
    },
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());

      // The glob above is only a cheap prefilter. `app/projects/[id]` is a real
      // page at the same path as the API, and this spec navigates straight to
      // it, so let actual page loads and Next.js client-side navigation (which
      // carries an `_rsc` param) through untouched.
      const isRscNavigation = url.searchParams.has("_rsc");
      const isDataRequest = ["fetch", "xhr"].includes(request.resourceType());
      if (isRscNavigation || !isDataRequest) {
        return route.continue();
      }

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
            storage_key: `org-1/project-1/${tenderDocumentId}/v1/tender.pdf`,
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
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/final-matrix` &&
        method === "GET"
      ) {
        return json([
          finalMatrixRow(),
          {
            ...finalMatrixRow(),
            serial: 2,
            requirement_id: otherRequirementId,
            source_page: null,
            tender_requirement: "Page location has not been established.",
          },
        ]);
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/requirements` &&
        method === "GET"
      ) {
        return json({
          items: [{
            id: otherRequirementId,
            requirement_type: "performance",
            normalized_text: "Another requirement from the first list page.",
            uncertainty: "low",
            review_state: "reviewed",
            ocr_warning: false,
            clause_number: "4.2",
            display_order: 1,
            mandatory: true,
            superseded: false,
            created_at: createdAt,
          }],
          total: 201,
          limit: 200,
          offset: 0,
        });
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/requirements/${requirementId}` &&
        method === "GET"
      ) {
        return json({
          id: requirementId,
          document_version_id: "tender-version-1",
          requirement_type: "performance",
          normalized_text: finalMatrixRow().tender_requirement,
          raw_source: finalMatrixRow().raw_source,
          uncertainty: "low",
          review_state: "reviewed",
          ocr_warning: false,
          clause_number: "4.2",
          reconciliation_group_id: null,
          display_order: 1,
          mandatory: true,
          superseded: false,
          created_at: createdAt,
          updated_at: null,
          constraints: [],
          sources: [{
            id: firstSourceId,
            requirement_id: requirementId,
            page_number: 12,
            clause_number: "4.2",
            location_type: "exact",
            source_text: finalMatrixRow().raw_source,
            quote_text: finalMatrixRow().raw_source,
            ocr_confidence: 0.99,
          }, {
            id: secondSourceId,
            requirement_id: requirementId,
            page_number: 14,
            clause_number: "4.3",
            location_type: "approximate",
            source_text: secondSourceQuote,
            quote_text: secondSourceQuote,
            ocr_confidence: 0.81,
          }, {
            id: thirdSourceId,
            requirement_id: requirementId,
            page_number: 14,
            clause_number: "4.4",
            location_type: "approximate",
            source_text: thirdSourceQuote,
            quote_text: thirdSourceQuote,
            ocr_confidence: 0.81,
          }],
          revisions: [],
          notes: [],
          categories: [],
        });
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/pages/12` &&
        method === "GET"
      ) {
        return json({
          page_number: 12,
          has_image: false,
          ocr_needed: false,
          ocr_confidence: 0.99,
          cleaned_text: finalMatrixRow().raw_source,
          extracted_text: finalMatrixRow().raw_source,
          structural_metadata: null,
          created_at: createdAt,
        });
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/pages/12/sources` &&
        method === "GET"
      ) {
        return json([{
          anchor_id: firstSourceId,
          requirement_id: requirementId,
          clause_number: "4.2",
          page_number: 12,
          location_type: "exact",
          source_text: finalMatrixRow().raw_source,
          quote_text: finalMatrixRow().raw_source,
          bbox: null,
          ocr_confidence: 0.99,
        }]);
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/pages/14` &&
        method === "GET"
      ) {
        return json({
          page_number: 14,
          has_image: true,
          ocr_needed: true,
          ocr_confidence: 0.81,
          cleaned_text: `${secondSourceQuote} ${thirdSourceQuote}`,
          extracted_text: `${secondSourceQuote} ${thirdSourceQuote}`,
          structural_metadata: null,
          created_at: createdAt,
        });
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/pages/14/sources` &&
        method === "GET"
      ) {
        return json([{
          anchor_id: secondSourceId,
          requirement_id: requirementId,
          clause_number: "4.3",
          page_number: 14,
          location_type: "approximate",
          source_text: secondSourceQuote,
          quote_text: secondSourceQuote,
          bbox: { x: 10, y: 10, width: 60, height: 12 },
          ocr_confidence: 0.81,
        }, {
          anchor_id: thirdSourceId,
          requirement_id: requirementId,
          clause_number: "4.4",
          page_number: 14,
          location_type: "approximate",
          source_text: thirdSourceQuote,
          quote_text: thirdSourceQuote,
          bbox: { x: 10, y: 30, width: 60, height: 12 },
          ocr_confidence: 0.81,
        }]);
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/pages/14/image` &&
        method === "GET"
      ) {
        return route.fulfill({
          status: 200,
          contentType: "image/svg+xml",
          body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="80" viewBox="0 0 100 80"><rect width="100" height="80" fill="#fff"/><path d="M5 5h90M5 20h90M5 35h90M5 50h90" stroke="#cbd5e1"/></svg>',
        });
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/pages/9` &&
        method === "GET"
      ) {
        return json({
          page_number: 9,
          has_image: false,
          ocr_needed: false,
          ocr_confidence: 0.99,
          cleaned_text: coverageQuote,
          extracted_text: coverageQuote,
          structural_metadata: null,
          created_at: createdAt,
        });
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/pages/9/sources` &&
        method === "GET"
      ) {
        expect(url.searchParams.get("quote")).toBe(coverageQuote);
        return json([{
          requirement_id: null,
          clause_number: null,
          page_number: 9,
          location_type: "approximate",
          source_text: coverageQuote,
          quote_text: coverageQuote,
          bbox: null,
          ocr_confidence: null,
        }]);
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/final-matrix/exports` &&
        method === "POST" &&
        url.searchParams.get("fmt") === "xlsx"
      ) {
        const artifact = {
          id: "review-required-export-1",
          status: "failed",
          export_format: "xlsx",
          generated_at: createdAt,
          requirement_count: 2,
          validation_status: "needs_review",
          validation_report: {
            issues: [],
            source_validation: { issues: [] },
            window_processing: {
              status: "complete",
              completeness_proven: false,
              obligation_audit_status: "potential_omissions",
              potential_omissions: [{ pages: [9], source_quote: coverageQuote }],
            },
          },
        };
        exportArtifacts.unshift(artifact);
        return json(artifact);
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/final-matrix/exports` &&
        method === "POST" &&
        url.searchParams.get("fmt") === "pdf"
      ) {
        return json({
          id: "image-validation-failed-export-1",
          status: "failed",
          export_format: "pdf",
          generated_at: createdAt,
          requirement_count: 2,
          validation_status: "needs_review",
          validation_report: {
            issues: [],
            source_validation: {
              status: "needs_review",
              checked_rows: 1,
              issues: [{ row_id: requirementId, code: "ocr_visual_verification_required" }],
              llm_fallback_results: [{
                row_id: requirementId,
                page_number: 12,
                status: "needs_review",
                call_status: "failed",
                error_category: "image_parse_error",
              }],
            },
            window_processing: {
              status: "complete",
              completeness_proven: false,
              obligation_audit_status: "no_potential_omissions",
              potential_omissions: [],
            },
          },
        });
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/exports` &&
        method === "GET"
      ) {
        return json(exportArtifacts);
      }
      if (path === "/projects/project-1/submissions/" && method === "GET") {
        return json([]);
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/final-matrix/exports` &&
        method === "POST" &&
        url.searchParams.get("template") === "vendor-response"
      ) {
        const artifact = {
          id: "vendor-response-export-1",
          status: "completed",
          export_format: "docx",
          generated_at: createdAt,
          requirement_count: 2,
          validation_status: "passed",
          validation_report: {
            artifact_integrity: "passed",
            expected_rows: 1,
            actual_rows: 1,
            checked_columns: 7,
            checked_cells: 7,
            issues: [],
            window_processing: {
              status: "not_available",
              completeness_proven: false,
              obligation_audit_status: "not_available",
            },
            source_validation: {
              status: "passed",
              checked_rows: 1,
              llm_assisted_rows: [],
              issues: [],
              calls: [],
            },
          },
        };
        exportArtifacts.unshift(artifact);
        return json(artifact);
      }
      if (
        path ===
          `/projects/project-1/documents/${tenderDocumentId}/versions/1/exports/vendor-response-export-1` &&
        method === "GET"
      ) {
        return route.fulfill({
          status: 200,
          contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          body: Buffer.from("browser smoke DOCX"),
        });
      }

      return json({ detail: `Unhandled browser smoke route: ${method} ${path}` }, 404);
    },
  );

  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      name: /Source-linked compliance sheets for technical tenders\./,
    })
  ).toBeVisible();
  await expect(
    page.getByText("PDF / DOCX in · XLSX / DOCX / PDF out")
  ).toBeVisible();

  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByLabel("Project name").fill("Pilot Tender");
  await page.getByRole("dialog").getByRole("button", { name: "Create project" }).click();

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
  await expect(page.getByText("Location unavailable")).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Open tender source for requirement 2/ })
  ).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Export XLSX" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export DOCX" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export PDF" })).toBeVisible();
  await page.getByRole("button", { name: "Export XLSX" }).click();
  await expect(page.getByText("Needs review", { exact: true })).toBeVisible();
  await expect(page.getByText("Unavailable", { exact: true })).toBeVisible();
  const findingLink = page.getByRole("link", {
    name: "Open tender page 9 and inspect excerpt",
  });
  await expect(findingLink).toBeVisible();
  await findingLink.click();
  await expect(page).toHaveURL(/page=9&sourceQuote=/);
  await expect(page.getByText("Page 9 · No rendered image", { exact: true })).toBeVisible();
  await expect(
    page.locator(".source-finding.selected").getByText(coverageQuote, { exact: true })
  ).toBeVisible();

  await page.goto("/projects/project-1/matrix");
  await expect(page.getByRole("heading", { name: "Final compliance sheet" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Export history" })).toBeVisible();
  await expect(page.getByText("Needs review", { exact: true })).toBeVisible();
  await expect(page.getByText(/This export is unavailable for download until it has a passing result\./)).toBeVisible();
  await expect(page.getByText("Unavailable", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download" })).toHaveCount(0);
  await page.getByRole("button", { name: "Export PDF" }).click();
  await expect(page.getByText(/Image validation error category: image_parse_error\./)).toBeVisible();
  const [vendorSheetDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Export vendor response DOCX" }).click(),
  ]);
  expect(vendorSheetDownload.suggestedFilename()).toBe("tender_vendor_response_v1.docx");
  await expect(page.getByText("Content checked", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("cell", { name: /Whole-tender completeness was not verified/ })
  ).toBeVisible();
  await page.getByRole("button", { name: "Refresh export history" }).click();
  await expect(page.getByText("Content checked", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("cell", { name: /Whole-tender completeness was not verified/ })
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Download" })).toHaveCount(1);
  const [historyDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Download" }).click(),
  ]);
  expect(historyDownload.suggestedFilename()).toBe("tender_export_v1_vendor-r.docx");
  await expect(page.getByRole("button", { name: "Create draft submission" })).toBeVisible();

  const sourceLink = page.getByRole("link", {
    name: "Open tender source for requirement 1, page 12",
  });
  await expect(sourceLink).toHaveAttribute(
    "href",
    `/projects/project-1/review?documentId=${tenderDocumentId}&version=1&requirementId=${requirementId}&page=12&sourceId=${firstSourceId}`
  );
  await sourceLink.click();
  const matrixEvidence = page.getByRole("dialog", { name: "Evidence" });
  await expect(matrixEvidence).toBeVisible();
  await expect(matrixEvidence).toContainText("Page 12");
  await expect(matrixEvidence).toContainText(finalMatrixRow().raw_source);
  await expect(matrixEvidence).toContainText("Exact source anchor");
  await matrixEvidence.getByRole("button", { name: "Close evidence panel" }).click();

  await page.goto(`/projects/project-1/review?documentId=${tenderDocumentId}&version=1&requirementId=${requirementId}&page=13`);
  await expect(
    page.getByText("Cited page is unavailable for this requirement")
  ).toBeVisible();

  await page.goto(`/projects/project-1/review?documentId=${tenderDocumentId}&version=2&requirementId=${requirementId}&page=12`);
  await expect(
    page.getByText(/The cited tender document version is unavailable/).first()
  ).toBeVisible();

  await page.goto(`/projects/project-1/review?documentId=${tenderDocumentId}&version=1&requirementId=${requirementId}&page=12&sourceId=${firstSourceId}`);
  await expect(page.getByText("Page 12 · No rendered image", { exact: true })).toBeVisible();
  await expect(
    page.locator(".source-finding.selected").getByText(finalMatrixRow().raw_source, { exact: true })
  ).toBeVisible();
  const citationChip = page.locator(".citation-chip").first();
  await citationChip.hover();
  const citationPreview = page.locator(".citation-glance").first();
  await expect(citationPreview).toContainText(finalMatrixRow().raw_source);
  await expect(citationPreview).toContainText("Exact anchor");
  await citationChip.click();
  const reviewEvidence = page.getByRole("dialog", { name: "Evidence" });
  await expect(reviewEvidence).toBeVisible();
  await expect(reviewEvidence).toContainText("Exact source anchor");
  await expect(reviewEvidence).toContainText(finalMatrixRow().raw_source);
  await reviewEvidence.getByRole("button", { name: "Close evidence panel" }).click();

  await page.getByRole("button", { name: "Open source on page 14, clause 4.3" }).click();
  await expect(page).toHaveURL(new RegExp(`page=14&sourceId=${secondSourceId}$`));
  await expect(page.getByAltText("Page 14 of Technical Tender v1")).toBeVisible();
  const selectedCitation = page.getByRole("dialog", { name: "Evidence" }).locator(".source-highlight.approximate.selected");
  await expect(selectedCitation).toHaveCount(1);
  await expect(selectedCitation).toHaveAttribute("title", `Approximate source: ${secondSourceQuote}`);
  await page.getByRole("dialog", { name: "Evidence" }).getByRole("button", { name: "Close evidence panel" }).click();

  await page.getByRole("button", { name: "Open source on page 14, clause 4.4" }).click();
  await expect(page).toHaveURL(new RegExp(`page=14&sourceId=${thirdSourceId}$`));
  const secondSelectedCitation = page.getByRole("dialog", { name: "Evidence" }).locator(".source-highlight.approximate.selected");
  await expect(secondSelectedCitation).toHaveCount(1);
  await expect(secondSelectedCitation).toHaveAttribute("title", `Approximate source: ${thirdSourceQuote}`);
  await expect(secondSelectedCitation.getByText("4.4Approx", { exact: true })).toBeVisible();
});
