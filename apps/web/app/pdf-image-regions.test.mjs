import test from "node:test";
import assert from "node:assert/strict";
import { OPS } from "pdfjs-dist/legacy/build/pdf.mjs";
import { collectPdfImageRegions, imageRegionNativeTextCoverage } from "./pdf-image-regions.ts";

const codes = {
  save: OPS.save,
  restore: OPS.restore,
  transform: OPS.transform,
  paintFormXObjectBegin: OPS.paintFormXObjectBegin,
  paintFormXObjectEnd: OPS.paintFormXObjectEnd,
  image: [OPS.paintImageXObject, OPS.paintInlineImageXObject, OPS.paintImageMaskXObject],
  imageGroup: [OPS.paintImageMaskXObjectGroup, OPS.paintInlineImageXObjectGroup],
  imageRepeat: [OPS.paintImageXObjectRepeat],
  imageMaskRepeat: [OPS.paintImageMaskXObjectRepeat],
};

test("maps image operator transforms into PDF.js viewport coordinates", () => {
  const regions = collectPdfImageRegions({
    fnArray: [OPS.save, OPS.transform, OPS.paintImageXObject, OPS.restore],
    argsArray: [null, [100, 0, 0, -50, 20, 60], ["image-1", 1200, 600], null],
    codes,
    viewportTransform: [1, 0, 0, -1, 0, 100],
    pageSize: { width: 200, height: 100 },
  });
  assert.deepEqual(regions, [{
    bbox: { x: 20, y: 40, width: 100, height: 50 },
    areaRatio: 0.25,
    operator: "image",
  }]);
});

test("respects saved graphics transforms and expands repeated images", () => {
  const regions = collectPdfImageRegions({
    fnArray: [OPS.save, OPS.transform, OPS.paintImageXObjectRepeat, OPS.restore, OPS.paintImageXObject],
    argsArray: [null, [1, 0, 0, 1, 10, 10], ["repeat", 20, -10, [0, 0, 30, 20]], null, ["outside", 1, 1]],
    codes,
    viewportTransform: [1, 0, 0, -1, 0, 100],
    pageSize: { width: 200, height: 100 },
  });
  assert.equal(regions.length, 3);
  assert.deepEqual(regions.map((region) => region.bbox), [
    { x: 10, y: 90, width: 20, height: 10 },
    { x: 40, y: 70, width: 20, height: 10 },
    { x: 0, y: 99, width: 1, height: 1 },
  ]);
});

test("reads PDF.js inline-image group transforms", () => {
  const regions = collectPdfImageRegions({
    fnArray: [OPS.save, OPS.paintInlineImageXObjectGroup, OPS.restore],
    argsArray: [null, [{ width: 100, height: 100 }, [
      { transform: [40, 0, 0, -20, 10, 80], x: 0, y: 0, w: 100, h: 100 },
      { transform: [30, 0, 0, -10, 120, 60], x: 100, y: 0, w: 100, h: 100 },
    ]], null],
    codes,
    viewportTransform: [1, 0, 0, -1, 0, 100],
    pageSize: { width: 200, height: 100 },
  });
  assert.deepEqual(regions.map((region) => region.bbox), [
    { x: 10, y: 20, width: 40, height: 20 },
    { x: 120, y: 40, width: 30, height: 10 },
  ]);
});

test("expands repeated image-mask transforms with skew and independent positions", () => {
  const regions = collectPdfImageRegions({
    fnArray: [OPS.paintImageMaskXObjectRepeat],
    argsArray: [["mask", 20, 2, 3, -10, [5, 30, 40, 60]]],
    codes,
    viewportTransform: [1, 0, 0, -1, 0, 100],
    pageSize: { width: 200, height: 100 },
  });
  assert.deepEqual(regions.map((region) => region.bbox), [
    { x: 5, y: 68, width: 23, height: 12 },
    { x: 40, y: 38, width: 23, height: 12 },
  ]);
});

test("measures native text overlap only inside the detected image region", () => {
  const region = { x: 0, y: 0, width: 100, height: 100 };
  assert.equal(imageRegionNativeTextCoverage(region, [{ x: 0, y: 0, width: 100, height: 20 }]), 0.2);
  assert.equal(imageRegionNativeTextCoverage(region, [{ x: 110, y: 0, width: 50, height: 20 }]), 0);
});
