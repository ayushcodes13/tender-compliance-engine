import test from "node:test";
import assert from "node:assert/strict";
import {
  getPdfDocumentCacheKey,
  getCachedPdfDocument,
  setCachedPdfDocument,
  clearPdfDocumentCache,
  calculateTargetScrollTop,
  getVisiblePageFromOffsets,
} from "./pdf-viewer-cache.ts";

test("generates deterministic cache keys from file attributes", () => {
  const key1 = getPdfDocumentCacheKey({ name: "tender.pdf", size: 1048576, lastModified: 1700000000000 });
  const key2 = getPdfDocumentCacheKey({ name: "tender.pdf", size: 1048576, lastModified: 1700000000000 });
  const keyDiff = getPdfDocumentCacheKey({ name: "tender-2.pdf", size: 1048576, lastModified: 1700000000000 });

  assert.equal(key1, key2);
  assert.notEqual(key1, keyDiff);
  assert.equal(key1, "tender.pdf:1048576:1700000000000");
});

test("stores, retrieves, and clears cached document promises", async () => {
  clearPdfDocumentCache();
  const mockPromise = Promise.resolve({ numPages: 42 });
  const key = "test-doc:123:456";

  assert.equal(getCachedPdfDocument(key), undefined);
  setCachedPdfDocument(key, mockPromise);
  assert.equal(getCachedPdfDocument(key), mockPromise);

  const doc = await getCachedPdfDocument(key);
  assert.equal(doc.numPages, 42);

  clearPdfDocumentCache();
  assert.equal(getCachedPdfDocument(key), undefined);
});

test("calculates target scroll top with and without bounding box", () => {
  const pageOffsetTop = 1500;
  const pageHeight = 1000;
  const stageHeight = 600;

  // No box: scrolls with comfortable margin to top of page
  const noBoxScroll = calculateTargetScrollTop(pageOffsetTop, pageHeight, null, stageHeight);
  assert.equal(noBoxScroll, 1500 - 24);

  // Box at 50% down page (y = 50% -> 500px inside page -> absolute 2000px)
  // Stage center offset = 600 * 0.38 = 228
  // Expected scroll = 2000 - 228 = 1772
  const boxScroll = calculateTargetScrollTop(
    pageOffsetTop,
    pageHeight,
    { x: 10, y: 50, width: 80, height: 5 },
    stageHeight
  );
  assert.equal(boxScroll, 1772);
});

test("identifies visible page from scroll offsets dynamically", () => {
  const pageTops = [
    { pageNumber: 1, top: 0, bottom: 999 },
    { pageNumber: 2, top: 1000, bottom: 1999 },
    { pageNumber: 3, top: 2000, bottom: 2999 },
  ];
  const stageHeight = 500; // viewCenter = currentScrollTop + 200

  // At top: scroll 0 -> viewCenter 200 -> Page 1
  assert.equal(getVisiblePageFromOffsets(pageTops, 0, stageHeight), 1);

  // Scrolled down: scroll 1200 -> viewCenter 1400 -> Page 2
  assert.equal(getVisiblePageFromOffsets(pageTops, 1200, stageHeight), 2);

  // Scrolled further: scroll 2200 -> viewCenter 2400 -> Page 3
  assert.equal(getVisiblePageFromOffsets(pageTops, 2200, stageHeight), 3);
});
