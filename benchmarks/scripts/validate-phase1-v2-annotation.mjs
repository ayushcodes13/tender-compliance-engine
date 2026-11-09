#!/usr/bin/env node
import { createHash } from "node:crypto";
import { execFile as execFileCallback } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { promisify } from "node:util";

const execFile = promisify(execFileCallback);
const MANIFEST_PATH = new URL("../phase-1-v2-corpus.json", import.meta.url);

export function normalizeWhitespace(value) {
  return value.replace(/\s+/gu, " ").trim();
}

export function quoteMatchesPage(anchor, pageText) {
  return normalizeWhitespace(pageText).includes(normalizeWhitespace(anchor.quote));
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export async function validateAnnotation(annotation, { sourcePath = null, manifest = null } = {}) {
  assert(isObject(annotation), "Annotation must be a JSON object.");
  assert(annotation.schemaVersion === 1 && annotation.protocolVersion === 1, "Unsupported annotation/protocol version.");
  assert(typeof annotation.annotationId === "string" && annotation.annotationId.trim(), "annotationId is required.");
  assert(["draft", "reviewed_pending_adjudication", "adjudicated", "unresolved"].includes(annotation.status), "Invalid annotation status.");
  assert(["development", "validation", "locked_evaluation"].includes(annotation.corpusSplit), "Invalid corpus split.");
  assert(isObject(annotation.source) && typeof annotation.source.documentId === "string" && annotation.source.documentId.trim(), "Source documentId is required.");
  assert(typeof annotation.source.fileName === "string" && annotation.source.fileName.trim(), "Source fileName is required.");
  assert(/^[a-f0-9]{64}$/u.test(annotation.source.sha256 ?? ""), "Source SHA-256 is required.");
  assert(Number.isInteger(annotation.source.physicalPageCount) && annotation.source.physicalPageCount > 0, "Source physicalPageCount is invalid.");
  assert(isObject(annotation.scope) && typeof annotation.scope.task === "string" && annotation.scope.task.trim(), "Scope task is required.");
  assert(typeof annotation.scope.statement === "string" && annotation.scope.statement.trim(), "Scope statement is required.");
  assert(typeof annotation.scope.wholeDocumentReviewed === "boolean", "Whole-document review state is required.");
  assert(Array.isArray(annotation.scope.physicalPagesReviewed) && annotation.scope.physicalPagesReviewed.length > 0, "At least one reviewed physical page is required.");
  assert(Array.isArray(annotation.anchors) && annotation.anchors.length > 0, "At least one source anchor is required.");
  assert(Array.isArray(annotation.regions) && annotation.regions.length > 0, "At least one source region is required.");
  assert(Array.isArray(annotation.labels) && annotation.labels.length > 0, "At least one obligation/non-requirement label is required.");
  assert(Array.isArray(annotation.disagreements) && Array.isArray(annotation.limitations), "Disagreements and limitations must be arrays.");
  assert(isObject(annotation.review) && typeof annotation.review.method === "string" && annotation.review.method.trim(), "Review method is required.");
  assert(typeof annotation.review.independentReviewComplete === "boolean" && typeof annotation.review.adjudicationNotes === "string", "Review/adjudication state is required.");
  assert(Array.isArray(annotation.review.reviewers) && annotation.review.reviewers.length > 0, "At least one reviewer record is required.");

  const ids = (items, field, label) => {
    const values = items.map((item) => item?.[field]);
    assert(values.every((value) => typeof value === "string" && value.trim()), `${label} IDs must be non-empty strings.`);
    assert(new Set(values).size === values.length, `${label} IDs must be unique.`);
    return new Set(values);
  };
  const anchorIds = ids(annotation.anchors, "id", "Anchor");
  const regionIds = ids(annotation.regions, "id", "Region");
  ids(annotation.labels, "id", "Label");

  for (const anchor of annotation.anchors) {
    assert(Number.isInteger(anchor.physicalPage) && anchor.physicalPage >= 1 && anchor.physicalPage <= annotation.source.physicalPageCount, `Anchor ${anchor.id} has invalid physical page.`);
    assert(typeof anchor.quote === "string" && anchor.quote.trim(), `Anchor ${anchor.id} has no literal quote.`);
    assert(["exact", "whitespace_normalized", "ocr_transcript", "visual_transcription", "unverified"].includes(anchor.quoteVerification), `Anchor ${anchor.id} has invalid quote verification.`);
    assert(["exact", "approximate", "page_only", "unknown"].includes(anchor.locationPrecision), `Anchor ${anchor.id} has invalid location precision.`);
    assert(typeof anchor.locationNote === "string" && anchor.locationNote.trim(), `Anchor ${anchor.id} needs a location note.`);
    if (anchor.locationPrecision === "exact") {
      assert(Array.isArray(anchor.sourceElementIds) && anchor.sourceElementIds.length > 0, `Exact anchor ${anchor.id} must name verified source element IDs.`);
      assert(Number.isInteger(anchor.startOffset) && Number.isInteger(anchor.endOffset) && anchor.startOffset < anchor.endOffset, `Exact anchor ${anchor.id} must have a valid source span.`);
    }
    if (anchor.startOffset !== undefined && anchor.endOffset !== undefined && anchor.startOffset !== null && anchor.endOffset !== null) {
      assert(anchor.startOffset < anchor.endOffset, `Anchor ${anchor.id} has an invalid offset range.`);
      assert(typeof anchor.offsetUnit === "string" && typeof anchor.offsetScope === "string", `Anchor ${anchor.id} offsets need unit and scope.`);
    }
  }

  for (const region of annotation.regions) {
    assert(Number.isInteger(region.physicalPage) && region.physicalPage >= 1 && region.physicalPage <= annotation.source.physicalPageCount, `Region ${region.id} has invalid physical page.`);
    assert(["paragraph", "table_row", "table_cell", "heading", "header_footer", "form", "image_region", "page_region", "other"].includes(region.kind), `Region ${region.id} has invalid kind.`);
    assert(typeof region.label === "string" && region.label.trim() && typeof region.reviewNote === "string" && region.reviewNote.trim(), `Region ${region.id} needs a label and review note.`);
    assert(["complete_in_scope", "partial", "unreviewed", "unreadable", "not_applicable"].includes(region.coverage), `Region ${region.id} has invalid coverage state.`);
    assert(Array.isArray(region.sourceAnchorIds) && region.sourceAnchorIds.every((id) => anchorIds.has(id)), `Region ${region.id} references an unknown anchor.`);
  }
  for (const page of annotation.scope.physicalPagesReviewed) {
    assert(Number.isInteger(page) && page >= 1 && page <= annotation.source.physicalPageCount, `Reviewed physical page ${page} is invalid.`);
  }
  assert(annotation.anchors.every((anchor) => annotation.scope.physicalPagesReviewed.includes(anchor.physicalPage)), "Every source anchor must fall within the declared reviewed-page scope.");
  assert(annotation.regions.every((region) => annotation.scope.physicalPagesReviewed.includes(region.physicalPage)), "Every source region must fall within the declared reviewed-page scope.");
  for (const printedPage of annotation.scope.printedPageLabels ?? []) {
    assert(Number.isInteger(printedPage.physicalPage) && annotation.scope.physicalPagesReviewed.includes(printedPage.physicalPage), "Printed page labels must refer to a reviewed physical page.");
    assert(typeof printedPage.printedLabel === "string" && printedPage.printedLabel.trim(), "Printed page label must be non-empty.");
  }
  if (annotation.scope.wholeDocumentReviewed) {
    const pages = new Set(annotation.scope.physicalPagesReviewed);
    assert(pages.size === annotation.source.physicalPageCount, "Whole-document review requires every physical page to be listed.");
    assert(!annotation.regions.some((region) => ["partial", "unreviewed"].includes(region.coverage)), "Whole-document review cannot include partial or unreviewed regions.");
    for (let page = 1; page <= annotation.source.physicalPageCount; page += 1) {
      assert(annotation.regions.some((region) => region.physicalPage === page && region.kind === "page_region"), `Whole-document review requires an explicit page coverage record for physical page ${page}.`);
    }
  }

  for (const label of annotation.labels) {
    assert(["technical_requirement", "service_fulfilment", "documentation_deliverable", "administrative_form", "explicit_non_requirement", "ambiguous", "unresolved"].includes(label.kind), `Label ${label.id} has invalid kind.`);
    assert(typeof label.interpretation === "string" && label.interpretation.trim(), `Label ${label.id} needs an interpretation.`);
    assert(["retain", "exclude_with_reason", "needs_adjudication", "unresolved"].includes(label.reviewDisposition), `Label ${label.id} has invalid review disposition.`);
    assert(Array.isArray(label.sourceAnchorIds) && label.sourceAnchorIds.length > 0 && label.sourceAnchorIds.every((id) => anchorIds.has(id)), `Label ${label.id} must reference known source anchors.`);
    assert(isObject(label.atomicity) && typeof label.atomicity.rationale === "string" && label.atomicity.rationale.trim(), `Label ${label.id} needs an atomicity rationale.`);
    assert(["independent", "grouped", "undetermined", "not_applicable"].includes(label.atomicity.status), `Label ${label.id} has invalid atomicity status.`);
    assert((label.atomicity.status === "grouped") === Boolean(typeof label.atomicity.groupId === "string" && label.atomicity.groupId.trim()), `Label ${label.id} must provide a groupId only when atomicity is grouped.`);
    assert(Array.isArray(label.values) && Array.isArray(label.conditions) && Array.isArray(label.modality) && Array.isArray(label.uncertainty), `Label ${label.id} is missing values/modality/conditions/uncertainty arrays.`);
    assert(label.conditions.every((item) => typeof item === "string") && label.modality.every((item) => typeof item === "string") && label.uncertainty.every((item) => typeof item === "string"), `Label ${label.id} has invalid condition, modality, or uncertainty entries.`);
    if (label.kind === "explicit_non_requirement") assert(label.reviewDisposition === "exclude_with_reason", `Non-requirement ${label.id} must carry an explicit exclusion disposition.`);
    if (label.reviewDisposition === "exclude_with_reason") assert(label.kind === "explicit_non_requirement", `Label ${label.id} cannot be excluded without an explicit non-requirement label.`);
    for (const value of label.values) assert(isObject(value) && typeof value.raw === "string" && value.raw.trim() && typeof value.role === "string" && value.role.trim(), `Label ${label.id} has an invalid raw value record.`);
  }
  for (const reviewer of annotation.review.reviewers) {
    assert(typeof reviewer.role === "string" && reviewer.role.trim() && Array.isArray(reviewer.regionIds), "Reviewer role and region coverage are required.");
    assert(/^\d{4}-\d{2}-\d{2}$/u.test(reviewer.date ?? ""), "Reviewer date must use YYYY-MM-DD.");
    assert(reviewer.regionIds.every((id) => regionIds.has(id)), "Reviewer references an unknown region.");
  }
  for (const disagreement of annotation.disagreements) assert(regionIds.has(disagreement.regionId), "Disagreement references an unknown region.");
  if (annotation.status === "adjudicated") {
    assert(annotation.review.independentReviewComplete === true && annotation.review.reviewers.length >= 2, "Adjudicated status requires at least two reviewers and completed independent review.");
    assert(annotation.disagreements.every((item) => typeof item.resolution === "string" && item.resolution.trim()), "Adjudicated annotations must resolve every recorded disagreement.");
    assert(!annotation.labels.some((label) => ["needs_adjudication", "unresolved"].includes(label.reviewDisposition)), "Adjudicated annotations cannot retain labels needing adjudication or unresolved.");
  }

  if (manifest) {
    const document = manifest.documents?.find((item) => item.id === annotation.source.documentId);
    assert(document && document.sha256 === annotation.source.sha256, "Annotation source identity/hash does not match the corpus manifest.");
    assert(document.split === annotation.corpusSplit, "Annotation split does not match the corpus manifest.");
    assert(document.physicalPages === annotation.source.physicalPageCount, "Annotation page count does not match the corpus manifest.");
  }

  let sourceAnchorsVerified = 0;
  let sourceAnchorsUnverified = 0;
  if (sourcePath) {
    const bytes = await readFile(sourcePath);
    const fingerprint = createHash("sha256").update(bytes).digest("hex");
    assert(fingerprint === annotation.source.sha256, "Source file SHA-256 does not match the annotation.");
    const { stdout: info } = await execFile("pdfinfo", [sourcePath], { maxBuffer: 128 * 1024 });
    const pageCount = Number(/^Pages:\s+(\d+)$/mu.exec(info)?.[1]);
    assert(pageCount === annotation.source.physicalPageCount, "Source PDF page count does not match the annotation.");
    const pageTextCache = new Map();
    for (const anchor of annotation.anchors) {
      if (anchor.quoteVerification === "unverified") {
        sourceAnchorsUnverified += 1;
        continue;
      }
      assert(["exact", "whitespace_normalized"].includes(anchor.quoteVerification), `Anchor ${anchor.id} requires a modality-specific verifier that is not implemented by this CLI.`);
      if (!pageTextCache.has(anchor.physicalPage)) {
        const { stdout } = await execFile("pdftotext", ["-f", String(anchor.physicalPage), "-l", String(anchor.physicalPage), "-layout", "-enc", "UTF-8", sourcePath, "-"], { maxBuffer: 4 * 1024 * 1024, encoding: "utf8" });
        pageTextCache.set(anchor.physicalPage, normalizeWhitespace(stdout));
      }
      assert(quoteMatchesPage(anchor, pageTextCache.get(anchor.physicalPage)), `Anchor ${anchor.id} was not found on physical page ${anchor.physicalPage}.`);
      sourceAnchorsVerified += 1;
    }
    const anchorsById = new Map(annotation.anchors.map((anchor) => [anchor.id, anchor]));
    for (const label of annotation.labels) {
      for (const value of label.values) {
        assert(typeof value.raw === "string" && value.raw.trim(), `Label ${label.id} has an empty raw value token.`);
        const normalizedValue = normalizeWhitespace(value.raw);
        const foundInCitedQuote = label.sourceAnchorIds
          .map((anchorId) => anchorsById.get(anchorId))
          .some((anchor) => anchor && normalizeWhitespace(anchor.quote).includes(normalizedValue));
        assert(foundInCitedQuote, `Raw value ${JSON.stringify(value.raw)} in label ${label.id} is not present in its cited source anchors.`);
      }
    }
  }
  return { annotationId: annotation.annotationId, status: annotation.status, corpusSplit: annotation.corpusSplit, pagesReviewed: annotation.scope.physicalPagesReviewed.length, regions: annotation.regions.length, labels: annotation.labels.length, sourceAnchorsVerified, sourceAnchorsUnverified };
}

async function main() {
  const args = process.argv.slice(2);
  let annotationPath = "";
  let sourcePath = null;
  for (let i = 0; i < args.length; i += 1) {
    if (args[i] === "--source" && args[i + 1]) sourcePath = args[++i];
    else if (!annotationPath && !args[i].startsWith("--")) annotationPath = args[i];
    else throw new Error("Usage: node benchmarks/scripts/validate-phase1-v2-annotation.mjs annotation.json [--source tender.pdf]");
  }
  assert(annotationPath, "Usage: node benchmarks/scripts/validate-phase1-v2-annotation.mjs annotation.json [--source tender.pdf]");
  const annotation = JSON.parse(await readFile(annotationPath, "utf8"));
  const manifest = JSON.parse(await readFile(MANIFEST_PATH, "utf8"));
  const result = await validateAnnotation(annotation, { sourcePath, manifest });
  process.stdout.write(`${JSON.stringify({ passed: true, ...result })}\n`);
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : "Annotation validation failed."}\n`);
    process.exitCode = 1;
  });
}
