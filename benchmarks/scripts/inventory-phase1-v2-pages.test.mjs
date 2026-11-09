import test from "node:test";
import assert from "node:assert/strict";
import { summarizePageInventory } from "./inventory-phase1-v2-pages.mjs";

test("page inventory summary counts parser signals without implying OCR completion", () => {
  const summary = summarizePageInventory([
    { pages: [
      { nativeTextChars: 20, imageRegionCount: 2, vectorTableGeometryCandidate: true, vectorRowCandidateCount: 3, nativeAnnexureHeadingCandidate: true, nativeTechnicalHeadingCandidate: false, currentRouterWouldRecommendOcr: true, currentRouterOcrTargetRegionCount: 1 },
      { nativeTextChars: 0, imageRegionCount: 1, vectorTableGeometryCandidate: false, vectorRowCandidateCount: 0, nativeAnnexureHeadingCandidate: false, nativeTechnicalHeadingCandidate: false, currentRouterWouldRecommendOcr: true, currentRouterOcrTargetRegionCount: 1 },
    ] },
  ]);

  assert.deepEqual(summary, {
    documents: 1,
    pages: 2,
    pagesWithNativeText: 1,
    pagesWithRasterImageSignals: 2,
    pagesWithBothTextAndRasterSignals: 1,
    pagesWithVectorTableGeometryCandidates: 1,
    pagesWithVectorRowCandidates: 1,
    vectorRowCandidates: 3,
    pagesWithNativeAnnexureHeadingCandidates: 1,
    pagesWithNativeTechnicalHeadingCandidates: 0,
    pagesRecommendedForOcrByCurrentRouter: 2,
    selectedImageRegionsByCurrentRouter: 2,
    ocrExecuted: false,
    modelCalls: 0,
    sourceTextStored: false,
  });
});

test("page inventory aggregation handles an empty corpus without fabricated coverage", () => {
  const summary = summarizePageInventory([]);
  assert.equal(summary.pages, 0);
  assert.equal(summary.pagesRecommendedForOcrByCurrentRouter, 0);
  assert.equal(summary.ocrExecuted, false);
});
