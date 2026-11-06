import test from "node:test";
import assert from "node:assert/strict";
import { createCanvas } from "@napi-rs/canvas";
import { jsPDF } from "jspdf";
import { getDocument, OPS } from "pdfjs-dist/legacy/build/pdf.mjs";
import { PDF_FONT_OPTIONS } from "./pdf-runtime.ts";
import { hasRasterImageOperators, shouldRunPageOcr } from "./ocr-routing.ts";
import { collectPdfImageRegions } from "./pdf-image-regions.ts";

const imageRegionCodes = {
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

test("recognizes PDF.js image-group operators as raster image content", () => {
  assert.equal(hasRasterImageOperators([OPS.paintInlineImageXObjectGroup], [OPS.paintInlineImageXObjectGroup]), true);
  assert.equal(hasRasterImageOperators([OPS.paintImageMaskXObjectGroup], [OPS.paintImageMaskXObjectGroup]), true);
});

test("detects OCR need on a hybrid page with a selectable header and scanned table image", async () => {
  const pdf = new jsPDF({ unit: "pt", format: "a4" });
  const header = "INSTITUTE OF ADVANCED INSTRUMENTATION · TECHNICAL TENDER · PAGE 14";
  pdf.setFontSize(10);
  pdf.text(header, 36, 34);

  const scan = createCanvas(1200, 1500);
  const context = scan.getContext("2d");
  context.fillStyle = "#fff";
  context.fillRect(0, 0, scan.width, scan.height);
  context.fillStyle = "#111";
  context.font = "bold 42px Arial";
  context.fillText("Technical parameters", 70, 110);
  context.font = "36px Arial";
  context.fillText("Maximum operating pressure: 500 bar", 70, 220);
  context.fillText("Supply voltage: 230 V AC", 70, 330);
  pdf.addImage(scan.toDataURL("image/jpeg", 0.92), "JPEG", 28, 54, 539, 674);

  const task = getDocument({ data: new Uint8Array(pdf.output("arraybuffer")), isEvalSupported: false, ...PDF_FONT_OPTIONS });
  const document = await task.promise;
  try {
    const page = await document.getPage(1);
    const viewport = page.getViewport({ scale: 1 });
    const content = await page.getTextContent({ disableNormalization: true });
    const textItems = content.items.filter((item) => "str" in item && item.str.trim());
    const selectableText = textItems.map((item) => item.str).join(" ");
    const textAreaRatio = textItems.reduce((total, item) => total + item.width * item.height, 0) / (viewport.width * viewport.height);
    const operatorList = await page.getOperatorList();
    const imageOperators = [OPS.paintImageXObject, OPS.paintInlineImageXObject, OPS.paintImageMaskXObject, OPS.paintImageXObjectRepeat, OPS.paintImageMaskXObjectRepeat];
    assert.ok(selectableText.length > 40, "the native header exceeds the old character threshold");
    assert.ok(hasRasterImageOperators(operatorList.fnArray, imageOperators));
    const imageRegions = collectPdfImageRegions({
      fnArray: operatorList.fnArray,
      argsArray: operatorList.argsArray,
      codes: imageRegionCodes,
      viewportTransform: viewport.transform,
      pageSize: { width: viewport.width, height: viewport.height },
    });
    assert.equal(imageRegions.length, 1);
    assert.ok(Math.abs(imageRegions[0].bbox.x - 28) < 1);
    assert.ok(Math.abs(imageRegions[0].bbox.y - 54) < 1);
    assert.ok(Math.abs(imageRegions[0].bbox.width - 539) < 1);
    assert.ok(Math.abs(imageRegions[0].bbox.height - 674) < 1);
    // The page-level transcript area is dense, but the scanned table image
    // contains almost no native text and must independently trigger OCR.
    assert.equal(shouldRunPageOcr({
      selectableText,
      textAreaRatio: 0.22,
      hasRasterImageContent: true,
      imageRegions,
      nativeTextBoxes: [],
    }), true);
    assert.equal(shouldRunPageOcr({ selectableText, textAreaRatio, hasRasterImageContent: true }), true);
    assert.equal(shouldRunPageOcr({ selectableText, textAreaRatio, hasRasterImageContent: false }), false);
    page.cleanup();
  } finally {
    await document.destroy();
  }
});

test("does not OCR dense native text pages just because they contain an image", () => {
  assert.equal(shouldRunPageOcr({ selectableText: "A long native technical schedule".repeat(50), textAreaRatio: 0.22, hasRasterImageContent: true }), false);
  assert.equal(shouldRunPageOcr({
    selectableText: "A long native technical schedule".repeat(50),
    textAreaRatio: 0.22,
    hasRasterImageContent: true,
    imageRegions: [{ bbox: { x: 350, y: 0, width: 200, height: 90 }, areaRatio: 0.037 }],
    nativeTextBoxes: [],
  }), false, "small repeated image marks should not trigger whole-page OCR by themselves");
  assert.equal(shouldRunPageOcr({
    selectableText: "A long native technical schedule".repeat(50),
    textAreaRatio: 0.22,
    hasRasterImageContent: true,
    imageRegions: [{ bbox: { x: 20, y: 20, width: 400, height: 500 }, areaRatio: 0.55 }],
    nativeTextBoxes: [{ x: 20, y: 20, width: 400, height: 500 }],
  }), false, "dense native text contained inside the image region does not trigger duplicate OCR");
    assert.equal(shouldRunPageOcr({ selectableText: "A short native header", textAreaRatio: 0.02, hasRasterImageContent: false }), true);
});
