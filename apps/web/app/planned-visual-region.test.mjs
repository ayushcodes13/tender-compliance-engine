import assert from "node:assert/strict";
import test from "node:test";
import { imageRegionCropRect } from "./planned-visual-region.ts";

test("maps approximate PDF.js image bounds into a padded crop at rendered-image scale", () => {
  assert.deepEqual(imageRegionCropRect({
    bbox: { x: 100, y: 200, width: 300, height: 100 },
    pageSize: { width: 600, height: 800 },
    imageSize: { width: 1500, height: 2000 },
  }), { left: 223, top: 491, right: 1027, bottom: 759 });
});

test("clamps crops to image bounds and rejects invalid or off-page geometry", () => {
  assert.deepEqual(imageRegionCropRect({
    bbox: { x: -5, y: 790, width: 40, height: 30 },
    pageSize: { width: 600, height: 800 },
    imageSize: { width: 600, height: 800 },
  }), { left: 0, top: 788, right: 37, bottom: 800 });
  assert.equal(imageRegionCropRect({
    bbox: { x: 700, y: 20, width: 30, height: 30 }, pageSize: { width: 600, height: 800 }, imageSize: { width: 1200, height: 1600 },
  }), null);
  assert.equal(imageRegionCropRect({
    bbox: { x: 10, y: 10, width: Number.NaN, height: 20 }, pageSize: { width: 600, height: 800 }, imageSize: { width: 1200, height: 1600 },
  }), null);
});
