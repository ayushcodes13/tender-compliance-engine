import test from "node:test";
import assert from "node:assert/strict";
import {
  buildRequirementSourceReference,
  buildSourcePageModel,
  createSourceDocumentModel,
  findUniqueSourceText,
  validateSourceDocumentInventory,
} from "./source-document.ts";

test("creates a stable document fingerprint and a distinct version identity", () => {
  const first = createSourceDocumentModel(new Uint8Array([1, 2, 3]), 2);
  const same = createSourceDocumentModel(new Uint8Array([1, 2, 3]), 2);
  const changed = createSourceDocumentModel(new Uint8Array([1, 2, 4]), 2);
  assert.equal(first.fingerprint, same.fingerprint);
  assert.equal(first.documentId, same.documentId);
  assert.notEqual(first.fingerprint, changed.fingerprint);
  assert.equal(first.documentVersionId, `ver-${first.fingerprint}`);
  assert.equal(first.pageCount, 2);
});

test("accepts a complete inventory with exact native spans and source structure", () => {
  const document = createSourceDocumentModel(new Uint8Array([13]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 1,
    width: 300,
    height: 400,
    sourceText: "Header\nForce ≥ 300 kN",
    positionedItems: [
      { start: 0, end: 6, text: "Header", box: { x: 10, y: 10, width: 30, height: 8 } },
      { start: 7, end: 21, text: "Force ≥ 300 kN", box: { x: 10, y: 20, width: 90, height: 8 } },
    ],
    imageRegions: [{ bbox: { x: 150, y: 30, width: 100, height: 120 }, areaRatio: 0.1, operator: "image" }],
    ocrRegions: [{ text: "Scanned note", bbox: { x: 160, y: 40, width: 60, height: 10 }, confidence: 92, confidenceLevel: "high", imageRegionIndex: 0 }],
    vectorRows: [{ cells: ["Force", "≥ 300 kN"], cellBoxes: [null, { x: 50, y: 20, width: 50, height: 8 }] }],
  });
  document.pages.push(page);
  assert.deepEqual(validateSourceDocumentInventory(document), []);
  assert.equal(page.imageRegions[0].ocrDisposition, "text-found", "an exact OCR-to-image link records region OCR coverage");
});

test("preserves selected image-region OCR outcomes and explicit skip reasons", () => {
  const document = createSourceDocumentModel(new Uint8Array([21]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 1,
    width: 300,
    height: 400,
    sourceText: "Header",
    positionedItems: [{ start: 0, end: 6, text: "Header", box: { x: 5, y: 5, width: 20, height: 5 } }],
    imageRegions: [
      { bbox: { x: 20, y: 80, width: 100, height: 80 }, areaRatio: 0.1, operator: "image", ocrDisposition: "no-text-found" },
      { bbox: { x: 150, y: 80, width: 100, height: 80 }, areaRatio: 0.1, operator: "image", ocrDisposition: "not-attempted", ocrSkipReason: "time-budget" },
      { bbox: { x: 20, y: 200, width: 10, height: 10 }, areaRatio: 0.001, operator: "image", ocrDisposition: "not-targeted" },
    ],
  });
  document.pages.push(page);
  assert.deepEqual(page.imageRegions.map((region) => [region.ocrDisposition, region.ocrSkipReason]), [
    ["no-text-found", undefined], ["not-attempted", "time-budget"], ["not-targeted", undefined],
  ]);
  assert.deepEqual(validateSourceDocumentInventory(document), []);
  page.imageRegions[1].ocrSkipReason = undefined;
  assert.ok(validateSourceDocumentInventory(document).some((issue) => issue.code === "invalid_image_region_ocr_state"));
});

test("reports incomplete pages, invalid text spans, duplicate IDs, and broken source links", () => {
  const document = createSourceDocumentModel(new Uint8Array([14]), 2);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 1,
    width: 300,
    height: 400,
    sourceText: "Header",
    positionedItems: [{ start: 0, end: 6, text: "Header", box: { x: 10, y: 10, width: 30, height: 8 } }],
    imageRegions: [{ bbox: { x: 100, y: 100, width: 50, height: 50 }, areaRatio: 0.02, operator: "image" }],
    ocrRegions: [{ text: "OCR", bbox: { x: 105, y: 110, width: 20, height: 5 }, confidence: 80, confidenceLevel: "medium", imageRegionIndex: 0 }],
    vectorRows: [{ cells: ["Parameter", "Value"], cellBoxes: [null, null] }],
  });
  page.physicalPdfPageNumber = 2;
  page.textBlocks[0].text = "Forged";
  page.ocrRegions[0].imageRegionId = `${page.id}:image:missing`;
  page.ocrRegions[0].id = page.textBlocks[0].id;
  page.tables[0].rows[0].cells[0].columnIndex = 1;
  document.pages.push(page);
  const issues = validateSourceDocumentInventory(document);
  assert.deepEqual(new Set(issues.map(({ code }) => code)), new Set([
    "page_count_mismatch", "missing_or_reordered_page", "invalid_text_span", "duplicate_source_element_id", "invalid_ocr_image_link",
    "invalid_table_relationship",
  ]));
});

test("preserves physical page text blocks with offsets, geometry, and source table cells", () => {
  const document = createSourceDocumentModel(new Uint8Array([7]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 3,
    width: 600,
    height: 800,
    sourceText: "Machine\n≥ 300 kN",
    positionedItems: [
      { start: 0, end: 7, text: "Machine", box: { x: 10, y: 20, width: 40, height: 8 } },
      { start: 8, end: 16, text: "≥ 300 kN", box: { x: 60, y: 20, width: 50, height: 8 } },
    ],
    vectorRows: [{ cells: ["Machine", "≥ 300 kN"], cellBoxes: [
      { x: 5, y: 10, width: 45, height: 15 }, { x: 50, y: 10, width: 70, height: 15 },
    ] }],
  });
  assert.equal(page.physicalPdfPageNumber, 3);
  assert.equal(page.printedPageNumber, undefined);
  assert.equal(page.coordinateSystem, "pdfjs-viewport-scale-1");
  assert.deepEqual(page.textBlocks.map((block) => [block.text, block.startOffset, block.endOffset]), [
    ["Machine", 0, 7], ["≥ 300 kN", 8, 16],
  ]);
  assert.equal(page.tables[0].rows[0].cells[1].sourceText, "≥ 300 kN");
  assert.equal(page.tables[0].rows[0].cells[1].bbox.x, 50);
});

test("matches normalized whitespace while keeping original source offsets and rejecting duplicate text", () => {
  const source = "Header\n  Range   ≥ 300 kN\nFooter";
  const match = findUniqueSourceText(source, "Range ≥ 300 kN");
  assert.ok(match);
  assert.equal(match.sourceText, "Range   ≥ 300 kN");
  assert.equal(source.slice(match.startOffset, match.endOffset), match.sourceText);
  assert.equal(findUniqueSourceText("Repeated\nRepeated", "Repeated"), null);
});

test("native references include exact quote offsets and source cell identity when known", () => {
  const document = createSourceDocumentModel(new Uint8Array([9]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 8,
    width: 300,
    height: 400,
    sourceText: "Parameter   Required\nForce   ≥ 300 kN",
    positionedItems: [],
    vectorRows: [{ cells: ["Force", "≥ 300 kN"], cellBoxes: [null, { x: 100, y: 30, width: 80, height: 12 }] }],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "≥ 300 kN", bbox: { x: 100, y: 30, width: 80, height: 12 },
    sourceCellLocation: { rowIndex: 0, columnIndex: 1 },
  });
  assert.equal(reference.physicalPdfPageNumber, 8);
  assert.equal(reference.locationPrecision, "exact");
  assert.equal(reference.sourceText, "≥ 300 kN");
  assert.equal(reference.documentFingerprint, document.fingerprint);
  assert.equal(reference.offsetUnit, "utf16-code-unit");
  assert.equal(reference.offsetScope, "page-source-text");
  assert.equal(reference.bboxCoordinateSystem, "pdfjs-viewport-scale-1");
  assert.equal(reference.sourceCell?.columnIndex, 1);
  assert.equal(reference.sourceCell?.rowId, page.tables[0].rows[0].id);
  assert.deepEqual(reference.sourceElementIds, [page.tables[0].id, page.tables[0].rows[0].id, page.tables[0].rows[0].cells[1].id]);
  assert.equal(reference.startOffset, 29);
  assert.equal(reference.endOffset, 37);
});

test("native narrative citations link every parser text block crossed by the exact source span", () => {
  const document = createSourceDocumentModel(new Uint8Array([12]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 6,
    width: 300,
    height: 400,
    sourceText: "Minimum\nforce ≥ 10 kN",
    positionedItems: [
      { start: 0, end: 7, text: "Minimum", box: { x: 10, y: 20, width: 40, height: 8 } },
      { start: 8, end: 21, text: "force ≥ 10 kN", box: { x: 10, y: 30, width: 70, height: 8 } },
    ],
  });
  const reference = buildRequirementSourceReference({
    document,
    page,
    quote: "Minimum force ≥ 10 kN",
    bbox: { x: 10, y: 20, width: 70, height: 18 },
  });

  assert.deepEqual(reference.sourceElementIds, page.textBlocks.map((block) => block.id));
  assert.equal(reference.sourceText, "Minimum\nforce ≥ 10 kN");
  assert.equal(reference.startOffset, 0);
  assert.equal(reference.endOffset, 21);
});

test("visual transcriptions keep OCR text separate from native context and omit invented offsets", () => {
  const document = createSourceDocumentModel(new Uint8Array([4]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId, physicalPdfPageNumber: 1, width: 100, height: 200,
    sourceText: "Capacity", positionedItems: [],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "Capacity ≥ 300 kN", bbox: { x: 1, y: 2, width: 30, height: 4 },
    visualTranscription: "Capacity ≥ 300 kN", selectableTextContext: "Capacity",
    ocrConfidence: "high",
  });
  assert.equal(reference.extractionMethod, "visual-transcription");
  assert.equal(reference.locationPrecision, "approximate");
  assert.equal(reference.sourceText, "Capacity");
  assert.equal(reference.transcribedText, "Capacity ≥ 300 kN");
  assert.equal(reference.ocrConfidence, "high");
  assert.equal("startOffset" in reference, false);
  assert.equal("endOffset" in reference, false);
});

test("stores local OCR regions separately from native text with approximate citations", () => {
  const document = createSourceDocumentModel(new Uint8Array([6]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId, physicalPdfPageNumber: 2, width: 200, height: 300,
    sourceText: "", positionedItems: [],
    ocrRegions: [{
      text: "Load capacity ≥ 300 kN",
      bbox: { x: 20, y: 40, width: 100, height: 12 },
      confidence: 78,
      confidenceLevel: "medium",
    }],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "Load capacity ≥ 300 kN", bbox: { x: 20, y: 40, width: 100, height: 12 },
    visualTranscription: "Load capacity ≥ 300 kN", transcriptionMethod: "tesseract-ocr", ocrConfidence: "medium",
  });

  assert.equal(page.sourceText, "");
  assert.equal(page.ocrText, "Load capacity ≥ 300 kN");
  assert.equal(page.extractionMethod, "tesseract-ocr");
  assert.equal(page.ocrRegions[0].extractionMethod, "tesseract-ocr");
  assert.deepEqual(page.ocrRegions[0].bbox, { x: 20, y: 40, width: 100, height: 12 });
  assert.equal(reference.sourceText, "");
  assert.equal(reference.transcribedText, "Load capacity ≥ 300 kN");
  assert.equal(reference.extractionMethod, "tesseract-ocr");
  assert.equal(reference.locationPrecision, "approximate");
  assert.equal(reference.ocrConfidence, "medium");
  assert.equal(reference.startOffset, undefined);
  assert.deepEqual(reference.sourceElementIds, [page.ocrRegions[0].id]);
});

test("stores raster image regions with stable page-scoped identities and approximate boxes", () => {
  const document = createSourceDocumentModel(new Uint8Array([11]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 2,
    width: 600,
    height: 800,
    sourceText: "Tender header",
    positionedItems: [],
    imageRegions: [{ bbox: { x: 20, y: 100, width: 400, height: 500 }, areaRatio: 5 / 12, operator: "image" }],
    ocrRegions: [{
      text: "Maximum pressure: 500 bar", bbox: { x: 25, y: 120, width: 120, height: 10 }, confidence: 80,
      confidenceLevel: "medium", imageRegionIndex: 0,
    }],
  });
  assert.equal(page.imageRegions[0].id, `${page.id}:image:1`);
  assert.deepEqual(page.imageRegions[0].bbox, { x: 20, y: 100, width: 400, height: 500 });
  assert.equal(page.imageRegions[0].areaRatio, 5 / 12);
  assert.equal(page.imageRegions[0].bboxPrecision, "approximate");
  assert.equal(page.ocrRegions[0].imageRegionId, page.imageRegions[0].id);
});

test("records native and OCR evidence together on a mixed-content page", () => {
  const document = createSourceDocumentModel(new Uint8Array([10]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 4,
    width: 600,
    height: 800,
    sourceText: "Institute of Testing · Page 4",
    positionedItems: [{ start: 0, end: 29, text: "Institute of Testing · Page 4", box: { x: 20, y: 20, width: 140, height: 10 } }],
    hasRasterImageContent: true,
    ocrRecommended: true,
    ocrStatus: "text-found",
    ocrRegions: [{
      text: "Maximum pressure: 500 bar",
      bbox: { x: 30, y: 90, width: 200, height: 14 },
      confidence: 72,
      confidenceLevel: "medium",
    }],
  });

  assert.equal(page.extractionMethod, "pdfjs-native-text");
  assert.equal(page.hasRasterImageContent, true);
  assert.equal(page.ocrRecommended, true);
  assert.equal(page.ocrStatus, "text-found");
  assert.equal(page.sourceText, "Institute of Testing · Page 4");
  assert.equal(page.ocrText, "Maximum pressure: 500 bar");
  assert.equal(page.textBlocks[0].text, page.sourceText);
  assert.equal(page.ocrRegions[0].text, page.ocrText);
});

test("distinguishes skipped, empty, and failed OCR from pages where OCR was not recommended", () => {
  const document = createSourceDocumentModel(new Uint8Array([11]), 1);
  const makePage = (options) => buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 1,
    width: 100,
    height: 200,
    sourceText: "Header",
    positionedItems: [],
    hasRasterImageContent: true,
    ocrRecommended: true,
    ...options,
  });

  const skipped = makePage({ ocrStatus: "not-attempted", ocrSkipReason: "engine-unavailable" });
  const empty = makePage({ ocrStatus: "no-text-found" });
  const failed = makePage({ ocrStatus: "failed" });
  const partial = makePage({ ocrStatus: "text-found", ocrSkipReason: "region-limit" });
  const ordinary = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 2,
    width: 100,
    height: 200,
    sourceText: "Native page text",
    positionedItems: [],
  });

  assert.equal(skipped.ocrStatus, "not-attempted");
  assert.equal(skipped.ocrSkipReason, "engine-unavailable");
  assert.match(skipped.warnings.join(" "), /recommended but not attempted/);
  assert.equal(empty.ocrStatus, "no-text-found");
  assert.match(empty.warnings.join(" "), /completed but found no text/);
  assert.equal(failed.ocrStatus, "failed");
  assert.match(failed.warnings.join(" "), /did not complete/);
  assert.match(partial.warnings.join(" "), /coverage is incomplete/);
  assert.equal(ordinary.ocrStatus, "not-recommended");
  assert.deepEqual(ordinary.warnings, []);
});

test("does not report an unmatched model quote as source text", () => {
  const document = createSourceDocumentModel(new Uint8Array([5]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId, physicalPdfPageNumber: 1, width: 100, height: 200,
    sourceText: "A different selectable sentence", positionedItems: [],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "A model suggestion that is not on the page", bbox: null,
  });
  assert.equal(reference.sourceText, "");
  assert.equal(reference.locationPrecision, "approximate");
  assert.equal(reference.startOffset, undefined);
});

test("literal text with no bounding box retains offsets but never claims an exact visual location", () => {
  const document = createSourceDocumentModel(new Uint8Array([8]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId, physicalPdfPageNumber: 11,
    width: 300, height: 400, sourceText: "The instrument shall withstand 5 bar.", positionedItems: [],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "The instrument shall withstand 5 bar.", bbox: null,
  });
  assert.equal(reference.sourceText, "The instrument shall withstand 5 bar.");
  assert.equal(reference.locationPrecision, "approximate");
  assert.equal(reference.bbox, null);
  assert.equal(reference.physicalPdfPageNumber, 11);
  assert.equal(reference.startOffset, 0);
  assert.equal(reference.endOffset, "The instrument shall withstand 5 bar.".length);
});


test("repeated native passages preserve literal page evidence but never fabricate an exact occurrence", () => {
  const document = createSourceDocumentModel(new Uint8Array([42]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 8,
    width: 300,
    height: 400,
    sourceText: "Speed 300 ± 10 mm/min\nOther clause\nSpeed 300 ± 10 mm/min",
    positionedItems: [
      { start: 0, end: 21, text: "Speed 300 ± 10 mm/min", box: { x: 10, y: 30, width: 140, height: 10 } },
      { start: 35, end: 56, text: "Speed 300 ± 10 mm/min", box: { x: 10, y: 90, width: 140, height: 10 } },
    ],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "Speed 300 ± 10 mm/min",
    bbox: { x: 10, y: 30, width: 140, height: 10 },
  });
  assert.equal(reference.sourceText, "Speed 300 ± 10 mm/min");
  assert.equal(reference.physicalPdfPageNumber, 8);
  assert.equal(reference.locationPrecision, "approximate", "a supplied box does not disambiguate repeated native text");
  assert.deepEqual(reference.sourceElementIds, []);
  assert.equal("startOffset" in reference, false);
  assert.equal("endOffset" in reference, false);
  assert.equal("sourceCell" in reference, false);
});

test("a different engineering sign or unit cannot be used to fill missing source evidence", () => {
  const document = createSourceDocumentModel(new Uint8Array([43]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 2,
    width: 300,
    height: 400,
    sourceText: "Power 5 mW\nAccuracy +2 mm\nPower 5 mW",
    positionedItems: [],
  });
  for (const quote of ["Power 5 MW", "Accuracy ±2 mm", "Power 50 mW"]) {
    const reference = buildRequirementSourceReference({ document, page, quote, bbox: null });
    assert.equal(reference.sourceText, "", quote);
    assert.deepEqual(reference.sourceElementIds, [], quote);
    assert.equal(reference.locationPrecision, "approximate", quote);
  }
});

test("visual transcriptions never borrow coincidentally similar native page text as proof", () => {
  const document = createSourceDocumentModel(new Uint8Array([44]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId, physicalPdfPageNumber: 3, width: 300, height: 400,
    sourceText: "Capacity 500 kN\nCapacity 500 kN", positionedItems: [],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "Capacity 500 kN", bbox: { x: 20, y: 20, width: 90, height: 10 },
    visualTranscription: "Capacity 500 kN", transcriptionMethod: "visual-transcription",
  });
  assert.equal(reference.sourceText, "");
  assert.equal(reference.transcribedText, "Capacity 500 kN");
  assert.deepEqual(reference.sourceElementIds, []);
  assert.equal(reference.locationPrecision, "approximate");
});
