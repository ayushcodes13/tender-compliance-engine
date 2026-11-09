import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { normalizeWhitespace, quoteMatchesPage, validateAnnotation } from "./validate-phase1-v2-annotation.mjs";

const annotationUrl = new URL("../phase-1-v2-annotations/iit-gandhinagar-page-22.json", import.meta.url);
const manifestUrl = new URL("../phase-1-v2-corpus.json", import.meta.url);
const annotation = JSON.parse(await readFile(annotationUrl, "utf8"));
const manifest = JSON.parse(await readFile(manifestUrl, "utf8"));

test("accepts the provisional page annotation and preserves review limits", async () => {
  const result = await validateAnnotation(annotation, { manifest });
  assert.equal(result.status, "draft");
  assert.equal(result.corpusSplit, "development");
  assert.equal(result.pagesReviewed, 1);
  assert.equal(result.sourceAnchorsVerified, 0);
  assert.equal(result.sourceAnchorsUnverified, 0);
  assert.equal(annotation.scope.wholeDocumentReviewed, false);
  assert.equal(annotation.review.independentReviewComplete, false);
});

test("matches only source quotes after whitespace normalization", () => {
  assert.equal(normalizeWhitespace("  Three   (03)\nyears warranty "), "Three (03) years warranty");
  assert.equal(quoteMatchesPage({ quote: "within 48 hours of the reporting time" }, "response within 48   hours\n of the reporting time."), true);
  assert.equal(quoteMatchesPage({ quote: "within 48 hours of the reporting time" }, "response within 24 hours of the reporting time."), false);
});

test("rejects an annotation whose split contradicts the corpus manifest", async () => {
  const changed = structuredClone(annotation);
  changed.corpusSplit = "locked_evaluation";
  await assert.rejects(validateAnnotation(changed, { manifest }), /split does not match/u);
});

test("rejects fabricated exact locations without parser evidence", async () => {
  const changed = structuredClone(annotation);
  changed.anchors[0].locationPrecision = "exact";
  await assert.rejects(validateAnnotation(changed, { manifest }), /must name verified source element IDs/u);
});

test("rejects adjudicated status without independent reviewers", async () => {
  const changed = structuredClone(annotation);
  changed.status = "adjudicated";
  await assert.rejects(validateAnnotation(changed, { manifest }), /requires at least two reviewers/u);
});

test("whole-document review requires an explicit reviewed region on every physical page", async () => {
  const changed = structuredClone(annotation);
  const pages = Array.from({ length: changed.source.physicalPageCount }, (_, index) => index + 1);
  changed.scope.physicalPagesReviewed = pages;
  changed.scope.wholeDocumentReviewed = true;
  changed.regions = pages.map((physicalPage) => ({
    id: `page-${physicalPage}-coverage`,
    physicalPage,
    kind: "page_region",
    label: `Page ${physicalPage} visual/source coverage record`,
    coverage: "complete_in_scope",
    sourceAnchorIds: [],
    reviewNote: "Synthetic validator-test coverage record.",
  }));
  changed.review.reviewers[0].regionIds = changed.regions.map((region) => region.id);

  const valid = await validateAnnotation(changed, { manifest });
  assert.equal(valid.pagesReviewed, changed.source.physicalPageCount);

  changed.regions.pop();
  changed.review.reviewers[0].regionIds = changed.regions.map((region) => region.id);
  await assert.rejects(validateAnnotation(changed, { manifest }), /explicit page coverage record for physical page 42/u);
});

test("whole-document review cannot silently contain partial or unreviewed regions", async () => {
  const changed = structuredClone(annotation);
  const pages = Array.from({ length: changed.source.physicalPageCount }, (_, index) => index + 1);
  changed.scope.physicalPagesReviewed = pages;
  changed.scope.wholeDocumentReviewed = true;
  changed.regions = pages.map((physicalPage) => ({
    id: `page-${physicalPage}-coverage`,
    physicalPage,
    kind: "page_region",
    label: `Page ${physicalPage} visual/source coverage record`,
    coverage: physicalPage === 7 ? "unreviewed" : "complete_in_scope",
    sourceAnchorIds: [],
    reviewNote: "Synthetic validator-test coverage record.",
  }));
  changed.review.reviewers[0].regionIds = changed.regions.map((region) => region.id);

  await assert.rejects(validateAnnotation(changed, { manifest }), /cannot include partial or unreviewed regions/u);

  changed.regions.find((region) => region.physicalPage === 7).coverage = "partial";
  await assert.rejects(validateAnnotation(changed, { manifest }), /cannot include partial or unreviewed regions/u);
});

test("rejects non-requirements that lack an explicit exclusion disposition", async () => {
  const changed = structuredClone(annotation);
  changed.labels.find((label) => label.kind === "explicit_non_requirement").reviewDisposition = "retain";
  await assert.rejects(validateAnnotation(changed, { manifest }), /must carry an explicit exclusion disposition/u);
});
