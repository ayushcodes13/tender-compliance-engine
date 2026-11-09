import assert from "node:assert/strict";
import test from "node:test";
import { resolveImageRegionDisposition, summarizeLayoutCharacterization } from "./characterize-phase1-v2-layout.mjs";

test("keeps not-targeted image regions distinct from selected but unattempted regions", () => {
  assert.deepEqual(resolveImageRegionDisposition({ targeted: false, pageOcrStatus: "text-found" }), { disposition: "not-targeted" });
  assert.deepEqual(resolveImageRegionDisposition({
    targeted: true,
    pageOcrStatus: "not-attempted",
    skipReason: "engine-unavailable",
  }), { disposition: "not-attempted", skipReason: "engine-unavailable" });
});

test("records failed OCR and completed region OCR without inferring page completeness", () => {
  assert.deepEqual(resolveImageRegionDisposition({ targeted: true, pageOcrStatus: "failed" }), { disposition: "failed" });
  assert.deepEqual(resolveImageRegionDisposition({
    targeted: true,
    pageOcrStatus: "text-found",
    attempted: true,
    textFound: true,
  }), { disposition: "text-found" });
  assert.deepEqual(resolveImageRegionDisposition({
    targeted: true,
    pageOcrStatus: "no-text-found",
    attempted: true,
    textFound: false,
  }), { disposition: "no-text-found" });
});

test("summarizes diagnostics while keeping parser and OCR measures bounded", () => {
  const summary = summarizeLayoutCharacterization([{
    sourceInventoryIssueCount: 0,
    sourceInventoryIssueCodes: {},
    pages: [{
      ocrStatus: "text-found",
      ocrInputMode: "full-page",
      ocrAttempted: true,
      ocrLineCount: 2,
      ocrWordCount: 7,
      vectorTableGeometryCandidate: true,
      vectorRowCandidateCount: 1,
      vectorCellTextCandidateCount: 3,
      imageRegions: [
        { disposition: "not-targeted", targeted: false },
        { disposition: "not-attempted", targeted: true },
      ],
    }],
  }]);

  assert.equal(summary.physicalPages, 1);
  assert.deepEqual(summary.pagesByOcrStatus, { "text-found": 1 });
  assert.deepEqual(summary.imageRegionsByDisposition, { "not-targeted": 1, "not-attempted": 1 });
  assert.equal(summary.targetedImageRegions, 1);
  assert.equal(summary.ocrExecuted, true);
  assert.equal(summary.modelCalls, 0);
  assert.equal(summary.ocrTextStored, false);
});
