import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { verifyVisualReview } from "./verify-phase1-v2-visual-review.mjs";

const manifest = JSON.parse(await readFile(new URL("../phase-1-v2-corpus.json", import.meta.url), "utf8"));
const artifact = JSON.parse(await readFile(new URL("../phase-1-v2-visual-review.json", import.meta.url), "utf8"));

test("matches source fingerprints and accounts for every physical page without overclaiming", () => {
  const result = verifyVisualReview(manifest, artifact);
  assert.equal(result.documents, 11);
  assert.equal(result.physicalPages, 367);
  assert.equal(result.independentReview, "pending");
  assert.equal(result.reviewLevel, "thumbnail-page-skim");
  assert.equal(result.renderConfirmedPageCoverage.length, 11);
  assert.deepEqual(result.renderConfirmedPageCoverage.find((document) => document.documentId === "example-input-3"), {
    documentId: "example-input-3",
    physicalPages: 41,
    uniquePagesReferenced: 40,
    pageRanges: [[1, 8], [10, 41]],
  });
  assert.equal(result.renderConfirmedUniquePageReferences, result.renderConfirmedPageCoverage.reduce((sum, document) => sum + document.uniquePagesReferenced, 0));
});

test("rejects a missing page range", () => {
  const changed = structuredClone(artifact);
  changed.documents[0].reviewedPageRanges = [[1, 10], [12, 29]];
  assert.throws(() => verifyVisualReview(manifest, changed), /page count does not match/u);
});

test("rejects overlapping page ranges", () => {
  const changed = structuredClone(artifact);
  changed.documents[0].reviewedPageRanges = [[1, 15], [15, 29]];
  assert.throws(() => verifyVisualReview(manifest, changed), /overlap/u);
});

test("rejects a document fingerprint mismatch", () => {
  const changed = structuredClone(artifact);
  changed.documents[0].sha256 = "0".repeat(64);
  assert.throws(() => verifyVisualReview(manifest, changed), /fingerprint mismatch/u);
});

test("rejects persisted source text and geometry", () => {
  const changed = structuredClone(artifact);
  changed.documents[0].sourceText = "must not be stored";
  assert.throws(() => verifyVisualReview(manifest, changed), /Forbidden source material/u);
});

test("rejects observations outside the fingerprinted document", () => {
  const changed = structuredClone(artifact);
  changed.documents[0].observations[0].pages = [30];
  assert.throws(() => verifyVisualReview(manifest, changed), /outside the source document/u);
});

test("requires unresolved structural questions to remain visible", () => {
  const changed = structuredClone(artifact);
  changed.documents[0].unknowns = [];
  assert.throws(() => verifyVisualReview(manifest, changed), /retain unresolved structural questions/u);
});

test("does not allow a single-reviewer observation to claim adjudication", () => {
  const changed = structuredClone(artifact);
  changed.documents[1].observations[1].evidenceLevel = "adjudicated";
  assert.throws(() => verifyVisualReview(manifest, changed), /evidence level is unsupported/u);
});
