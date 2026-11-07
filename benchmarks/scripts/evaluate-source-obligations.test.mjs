import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { reconcileSourceObligations } from "./evaluate-source-obligations.mjs";

const annotation = JSON.parse(await readFile(new URL("../representative-tenders/heldout-golden-v0.6.json", import.meta.url), "utf8"));
const syntheticOutput = JSON.parse(await readFile(new URL("../fixtures/iitg-page11-synthetic-output.json", import.meta.url), "utf8"));

test("reconciles independently identified obligations against source citations despite a no-gaps model claim", () => {
  const report = reconcileSourceObligations(annotation, syntheticOutput);
  assert.equal(report.summary.total, 7);
  assert.equal(report.summary.source_anchors_covered, 4);
  assert.equal(report.summary.no_source_anchor_match, 3);
  assert.equal(report.cases.find((item) => item.caseId === "iitg-page-11-five-year-amc-omitted").status, "no_source_anchor_match");
  assert.equal(report.cases.find((item) => item.caseId === "iitg-page-11-local-after-sales-presence-omitted").status, "no_source_anchor_match");
  assert.equal(report.cases.find((item) => item.caseId === "iitg-page-11-five-year-parts-support-omitted").status, "no_source_anchor_match");
  assert.equal(report.cases.find((item) => item.caseId === "iitg-page-11-operation-maintenance-manual-copies").status, "source_anchors_covered");
  assert.ok(report.limitations.some((item) => item.includes("no_gaps_reported")));
});

test("reports partial source-anchor coverage across separately cited output rows", () => {
  const caseOnly = { ...annotation, cases: [annotation.cases.find((item) => item.caseId === "iitg-page-11-operation-maintenance-manual-copies")] };
  const report = reconcileSourceObligations(caseOnly, {
    analysis: {
      document: { documentFingerprint: annotation.sourceSha256 },
      requirements: syntheticOutput.requirements.filter((row) => row.id === "synthetic-req-manual-1"),
    },
  });
  assert.equal(report.cases[0].status, "partial_source_anchors");
  assert.equal(report.cases[0].matchedAnchors, 1);
  assert.equal(report.cases[0].anchorCount, 3);
  assert.deepEqual(report.cases[0].anchorResults[0].requirementIds, ["synthetic-req-manual-1"]);
});

test("does not count model interpretation text or a citation from another page as source evidence", () => {
  const caseOnly = { ...annotation, cases: [annotation.cases.find((item) => item.caseId === "iitg-page-11-five-year-amc-omitted")] };
  const report = reconcileSourceObligations(caseOnly, {
    document: { documentFingerprint: annotation.sourceSha256 },
    requirements: [
      { id: "interpretation-only", page: 11, text: "Five-year annual maintenance contract with service visits and calibration." },
      {
        id: "wrong-page-citation",
        page: 10,
        sourceReference: {
          documentFingerprint: annotation.sourceSha256,
          physicalPdfPageNumber: 10,
          sourceText: annotation.cases[0].sourceAnchors[0],
        },
      },
    ],
  });
  assert.equal(report.cases[0].status, "no_source_anchor_match");
});

test("distinguishes an obligation with no recorded candidate from one generated and rejected", () => {
  const caseOnly = { ...annotation, cases: [annotation.cases.find((item) => item.caseId === "iitg-page-11-five-year-amc-omitted")] };
  const trace = {
    documentFingerprint: annotation.sourceSha256,
    candidates: [{
      candidateId: "cand-amc-rejected",
      documentFingerprint: annotation.sourceSha256,
      page: 11,
      sourceQuote: caseOnly.cases[0].sourceAnchors[0],
      sourceQuoteStatus: "matched",
      disposition: "rejected",
      responsibleStage: "source_evidence_validation",
      rejectionCategory: "source_quote_or_location_not_verified",
    }],
  };
  const output = { document: { documentFingerprint: annotation.sourceSha256 }, requirements: [], audit: { page11: "no_gaps_reported" } };
  const rejected = reconcileSourceObligations(caseOnly, output, trace);
  assert.equal(rejected.cases[0].anchorResults[0].traceStatus, "generated_rejected");
  assert.equal(rejected.cases[0].anchorResults[0].candidates[0].responsibleStage, "source_evidence_validation");
  assert.equal(rejected.cases[0].anchorResults[1].traceStatus, "not_generated");
});

test("rejects outputs whose source fingerprint differs from the annotation", () => {
  assert.throws(() => reconcileSourceObligations(annotation, { sourceSha256: "0".repeat(64), requirements: [] }), /does not match/);
});

test("rejects a forensic trace from a different tender", () => {
  assert.throws(() => reconcileSourceObligations(annotation, syntheticOutput, {
    documentFingerprint: "0".repeat(64),
    candidates: [],
  }), /must match the annotation/);
});

test("rejects trace candidates with a conflicting document fingerprint", () => {
  assert.throws(() => reconcileSourceObligations(annotation, syntheticOutput, {
    documentFingerprint: annotation.sourceSha256,
    candidates: [{ documentFingerprint: "0".repeat(64) }],
  }), /must match the annotation/);
});

test("ignores a row-level citation carrying a conflicting document fingerprint", () => {
  const caseOnly = { ...annotation, cases: [annotation.cases.find((item) => item.caseId === "iitg-page-11-operation-maintenance-manual-copies")] };
  const report = reconcileSourceObligations(caseOnly, {
    document: { documentFingerprint: annotation.sourceSha256 },
    requirements: [{
      id: "wrong-document-citation",
      sourceReference: {
        documentFingerprint: "0".repeat(64),
        physicalPdfPageNumber: 11,
        sourceText: caseOnly.cases[0].sourceAnchors.join(" "),
      },
    }],
  });
  assert.equal(report.cases[0].status, "no_source_anchor_match");
});
