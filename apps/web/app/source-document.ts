import { createHash } from "node:crypto";
import { alignExactTokenSequence, alignTokenSequence, findUniqueTokenBoundedMatch, hasTechnicalAgreement } from "./token-sequence-alignment.ts";

export type SourceBox = { x: number; y: number; width: number; height: number };

export type SourceTextBlock = {
  id: string;
  text: string;
  startOffset: number;
  endOffset: number;
  bbox: SourceBox | null;
  extractionMethod: "pdfjs-native-text" | "tesseract-ocr";
};

export type SourceOcrRegion = {
  id: string;
  text: string;
  bbox: SourceBox;
  confidence: number;
  confidenceLevel: "high" | "medium" | "low";
  extractionMethod: "tesseract-ocr";
  imageRegionId?: string;
};

export type SourceImageRegion = {
  id: string;
  bbox: SourceBox;
  areaRatio: number;
  operator: "image" | "image-group" | "image-repeat";
  bboxPrecision: "approximate";
  ocrDisposition: "not-targeted" | "not-attempted" | "text-found" | "no-text-found" | "failed";
  ocrSkipReason?: SourcePageOcrSkipReason;
};

export type SourceTableCell = {
  id: string;
  rowIndex: number;
  columnIndex: number;
  sourceText: string;
  bbox: SourceBox | null;
};

export type SourceTableRow = { id: string; rowIndex: number; cells: SourceTableCell[] };
export type SourceTable = { id: string; rows: SourceTableRow[]; columnCount: number };
export type SourcePageOcrStatus = "not-recommended" | "not-attempted" | "text-found" | "no-text-found" | "failed";
export type SourcePageOcrSkipReason = "engine-unavailable" | "page-limit" | "time-budget" | "region-limit";

export type SourcePageModel = {
  id: string;
  physicalPdfPageNumber: number;
  printedPageNumber?: number;
  width: number;
  height: number;
  coordinateSystem: "pdfjs-viewport-scale-1";
  sourceText: string;
  ocrText: string;
  hasRasterImageContent: boolean;
  ocrRecommended: boolean;
  ocrStatus: SourcePageOcrStatus;
  ocrSkipReason?: SourcePageOcrSkipReason;
  imageRegions: SourceImageRegion[];
  ocrRegions: SourceOcrRegion[];
  extractionMethod: "pdfjs-native-text" | "tesseract-ocr" | "no-selectable-text";
  textBlocks: SourceTextBlock[];
  tables: SourceTable[];
  warnings: string[];
};

export type SourceDocumentModel = {
  documentId: string;
  documentVersionId: string;
  fingerprint: string;
  pageCount: number;
  pages: SourcePageModel[];
};

export type SourceInventoryIssueCode =
  | "page_count_mismatch"
  | "missing_or_reordered_page"
  | "duplicate_source_element_id"
  | "invalid_text_span"
  | "invalid_geometry"
  | "invalid_ocr_image_link"
  | "invalid_image_region_ocr_state"
  | "invalid_table_relationship";

export type SourceInventoryIssue = { code: SourceInventoryIssueCode; page?: number; elementId?: string };

export type SourceCellLocation = { rowIndex: number; columnIndex: number };

export type RequirementSourceReference = {
  documentId: string;
  documentVersionId: string;
  documentFingerprint: string;
  physicalPdfPageNumber: number;
  sourceText: string;
  /** Stable IDs for the parser-owned text blocks, OCR regions, and table elements supporting this reference. */
  sourceElementIds: string[];
  startOffset?: number;
  endOffset?: number;
  offsetUnit?: "utf16-code-unit";
  offsetScope?: "page-source-text";
  bbox: SourceBox | null;
  bboxCoordinateSystem: "pdfjs-viewport-scale-1";
  extractionMethod: "pdfjs-native-text" | "visual-transcription" | "tesseract-ocr" | "operator-entered";
  locationPrecision: "exact" | "approximate";
  transcribedText?: string;
  ocrConfidence?: "high" | "medium" | "low";
  selectableTextContext?: string;
  sourceCell?: { tableId: string; rowId: string; cellId: string; rowIndex: number; columnIndex: number };
};

type PositionedSourceItem = { start: number; end: number; text: string; box: SourceBox };
type VectorCellInput = { text: string; bbox: SourceBox | null };
type VectorRowInput = { cells: string[]; cellBoxes: Array<SourceBox | null> };

export function buildSourceTables(pageId: string, vectorRows: VectorRowInput[]): SourceTable[] {
  if (!vectorRows.length) return [];
  return [{
    id: `${pageId}:table:vector:1`,
    rows: vectorRows.map((row, rowIndex) => ({
      id: `${pageId}:table:vector:1:row:${rowIndex + 1}`,
      rowIndex,
      cells: row.cells.map((sourceText, columnIndex) => ({
        id: `${pageId}:table:vector:1:row:${rowIndex + 1}:cell:${columnIndex + 1}`,
        rowIndex,
        columnIndex,
        sourceText,
        bbox: row.cellBoxes[columnIndex] ? { ...row.cellBoxes[columnIndex]! } : null,
      })),
    })),
    columnCount: Math.max(...vectorRows.map((row) => row.cells.length)),
  }];
}

export function createSourceDocumentModel(bytes: Uint8Array, pageCount: number): SourceDocumentModel {
  const fingerprint = createHash("sha256").update(bytes).digest("hex");
  return {
    documentId: `doc-${fingerprint.slice(0, 24)}`,
    documentVersionId: `ver-${fingerprint}`,
    fingerprint,
    pageCount,
    pages: [],
  };
}

/** Checks parser-owned inventory structure; it does not establish semantic coverage. */
export function validateSourceDocumentInventory(document: SourceDocumentModel): SourceInventoryIssue[] {
  const issues: SourceInventoryIssue[] = [];
  const issueKeys = new Set<string>();
  const addIssue = (issue: SourceInventoryIssue) => {
    const key = `${issue.code}:${issue.page ?? ""}:${issue.elementId ?? ""}`;
    if (!issueKeys.has(key)) { issueKeys.add(key); issues.push(issue); }
  };
  if (document.pages.length !== document.pageCount) addIssue({ code: "page_count_mismatch" });

  const seenIds = new Set<string>();
  const registerId = (id: string, page: number) => {
    if (seenIds.has(id)) addIssue({ code: "duplicate_source_element_id", page, elementId: id });
    seenIds.add(id);
  };
  const validBox = (box: SourceBox | null) => box === null || [box.x, box.y, box.width, box.height].every(Number.isFinite)
    && box.width > 0 && box.height > 0;

  document.pages.forEach((page, index) => {
    const expectedPageNumber = index + 1;
    if (page.physicalPdfPageNumber !== expectedPageNumber || page.id !== `${document.documentId}:page:${expectedPageNumber}`) {
      addIssue({ code: "missing_or_reordered_page", page: expectedPageNumber, elementId: page.id });
    }
    registerId(page.id, expectedPageNumber);
    if (![page.width, page.height].every(Number.isFinite) || page.width <= 0 || page.height <= 0) {
      addIssue({ code: "invalid_geometry", page: expectedPageNumber, elementId: page.id });
    }
    for (const block of page.textBlocks) {
      registerId(block.id, expectedPageNumber);
      const spanValid = Number.isInteger(block.startOffset) && Number.isInteger(block.endOffset)
        && block.startOffset >= 0 && block.endOffset >= block.startOffset
        && block.endOffset <= page.sourceText.length
        && page.sourceText.slice(block.startOffset, block.endOffset) === block.text;
      if (!spanValid) addIssue({ code: "invalid_text_span", page: expectedPageNumber, elementId: block.id });
      if (!validBox(block.bbox)) addIssue({ code: "invalid_geometry", page: expectedPageNumber, elementId: block.id });
    }
    const imageIds = new Set(page.imageRegions.map((region) => region.id));
    for (const region of page.imageRegions) {
      registerId(region.id, expectedPageNumber);
      if (!validBox(region.bbox) || !Number.isFinite(region.areaRatio) || region.areaRatio < 0 || region.areaRatio > 1) {
        addIssue({ code: "invalid_geometry", page: expectedPageNumber, elementId: region.id });
      }
      if ((region.ocrDisposition === "not-targeted" && Boolean(region.ocrSkipReason))
        || (region.ocrDisposition === "not-attempted" && !region.ocrSkipReason)
        || (region.ocrDisposition !== "not-attempted" && Boolean(region.ocrSkipReason))) {
        addIssue({ code: "invalid_image_region_ocr_state", page: expectedPageNumber, elementId: region.id });
      }
    }
    for (const region of page.ocrRegions) {
      registerId(region.id, expectedPageNumber);
      if (region.imageRegionId && !imageIds.has(region.imageRegionId)) {
        addIssue({ code: "invalid_ocr_image_link", page: expectedPageNumber, elementId: region.id });
      }
      const linkedImageRegion = page.imageRegions.find((imageRegion) => imageRegion.id === region.imageRegionId);
      if (linkedImageRegion && linkedImageRegion.ocrDisposition !== "text-found") {
        addIssue({ code: "invalid_image_region_ocr_state", page: expectedPageNumber, elementId: linkedImageRegion.id });
      }
      if (!validBox(region.bbox)) addIssue({ code: "invalid_geometry", page: expectedPageNumber, elementId: region.id });
    }
    if (page.ocrText !== page.ocrRegions.map((region) => region.text).join("\n")) {
      addIssue({ code: "invalid_text_span", page: expectedPageNumber, elementId: page.id });
    }
    for (const table of page.tables) {
      registerId(table.id, expectedPageNumber);
      if (!Number.isInteger(table.columnCount) || table.columnCount < 1 || table.rows.length === 0) {
        addIssue({ code: "invalid_table_relationship", page: expectedPageNumber, elementId: table.id });
      }
      for (const [rowOrder, row] of table.rows.entries()) {
        registerId(row.id, expectedPageNumber);
        if (row.rowIndex !== rowOrder || row.cells.length > table.columnCount) {
          addIssue({ code: "invalid_table_relationship", page: expectedPageNumber, elementId: row.id });
        }
        for (const [columnIndex, cell] of row.cells.entries()) {
          registerId(cell.id, expectedPageNumber);
          if (cell.rowIndex !== row.rowIndex || cell.columnIndex !== columnIndex || !validBox(cell.bbox)) {
            addIssue({ code: "invalid_table_relationship", page: expectedPageNumber, elementId: cell.id });
          }
        }
      }
    }
  });
  return issues;
}

export function buildSourcePageModel(input: {
  documentId: string;
  physicalPdfPageNumber: number;
  width: number;
  height: number;
  sourceText: string;
  positionedItems: PositionedSourceItem[];
  hasRasterImageContent?: boolean;
  ocrRecommended?: boolean;
  ocrStatus?: SourcePageOcrStatus;
  ocrSkipReason?: SourcePageOcrSkipReason;
  imageRegions?: Array<Omit<SourceImageRegion, "id" | "bboxPrecision" | "ocrDisposition"> & { ocrDisposition?: SourceImageRegion["ocrDisposition"] }>;
  ocrRegions?: Array<Omit<SourceOcrRegion, "id" | "extractionMethod" | "imageRegionId"> & { imageRegionIndex?: number }>;
  vectorRows?: VectorRowInput[];
}): SourcePageModel {
  const pageId = `${input.documentId}:page:${input.physicalPdfPageNumber}`;
  const textBlocks = input.positionedItems.map((item, index) => ({
    id: `${pageId}:text:${index + 1}`,
    text: input.sourceText.slice(item.start, item.end),
    startOffset: item.start,
    endOffset: item.end,
    bbox: item.box.width > 0 && item.box.height > 0 ? { ...item.box } : null,
    extractionMethod: "pdfjs-native-text" as const,
  }));
  const tables = buildSourceTables(pageId, input.vectorRows ?? []);
  const imageRegions: SourceImageRegion[] = (input.imageRegions ?? []).map((region, index) => ({
    ...region,
    id: `${pageId}:image:${index + 1}`,
    bbox: { ...region.bbox },
    bboxPrecision: "approximate",
    ocrDisposition: region.ocrDisposition ?? "not-targeted",
    ...(region.ocrSkipReason ? { ocrSkipReason: region.ocrSkipReason } : {}),
  }));
  const ocrRegions: SourceOcrRegion[] = (input.ocrRegions ?? []).map((region, index) => {
    const { imageRegionIndex, ...sourceRegion } = region;
    return {
      ...sourceRegion,
      id: `${pageId}:ocr:${index + 1}`,
      ...(imageRegionIndex === undefined ? {} : { imageRegionId: `${pageId}:image:${imageRegionIndex + 1}` }),
      bbox: { ...region.bbox },
      extractionMethod: "tesseract-ocr",
    };
  });
  imageRegions.forEach((region, index) => {
    if (!input.imageRegions?.[index]?.ocrDisposition && ocrRegions.some((ocrRegion) => ocrRegion.imageRegionId === region.id)) {
      region.ocrDisposition = "text-found";
    }
  });
  const ocrText = ocrRegions.map((region) => region.text).join("\n");
  const ocrRecommended = input.ocrRecommended ?? false;
  const ocrStatus = input.ocrStatus ?? (ocrRecommended ? "not-attempted" : "not-recommended");
  const warnings = input.sourceText.trim()
    ? []
    : ocrText.trim()
      ? ["No selectable text was found; OCR text and approximate regions are stored separately."]
      : ["No selectable text was found on this page."];
  if (ocrStatus === "not-attempted") {
    warnings.push(`OCR was recommended but not attempted${input.ocrSkipReason ? ` (${input.ocrSkipReason})` : ""}.`);
  } else if (input.ocrSkipReason) {
    warnings.push(`OCR coverage is incomplete (${input.ocrSkipReason}); inspect the remaining source image regions.`);
  } else if (ocrStatus === "failed") {
    warnings.push("OCR was attempted but did not complete; no OCR text was added to the source inventory.");
  } else if (ocrStatus === "no-text-found") {
    warnings.push("OCR completed but found no text regions.");
  }

  return {
    id: pageId,
    physicalPdfPageNumber: input.physicalPdfPageNumber,
    width: input.width,
    height: input.height,
    coordinateSystem: "pdfjs-viewport-scale-1",
    sourceText: input.sourceText,
    ocrText,
    hasRasterImageContent: input.hasRasterImageContent ?? false,
    ocrRecommended,
    ocrStatus,
    ...(input.ocrSkipReason ? { ocrSkipReason: input.ocrSkipReason } : {}),
    imageRegions,
    ocrRegions,
    extractionMethod: input.sourceText.trim() ? "pdfjs-native-text" : ocrText.trim() ? "tesseract-ocr" : "no-selectable-text",
    textBlocks,
    tables,
    warnings,
  };
}

export function findUniqueSourceText(rawText: string, quote: string): { startOffset: number; endOffset: number; sourceText: string } | null {
  return findUniqueTokenBoundedMatch(rawText, quote);
}

export function buildRequirementSourceReference(input: {
  document: SourceDocumentModel;
  page: SourcePageModel;
  quote: string;
  bbox: SourceBox | null;
  visualTranscription?: string;
  transcriptionMethod?: "visual-transcription" | "tesseract-ocr";
  ocrConfidence?: "high" | "medium" | "low";
  selectableTextContext?: string;
  sourceCellLocation?: SourceCellLocation;
  /** Exact parser span identified by a source-bound planner unit when page-wide text is repeated. */
  selectedSourceSpan?: { sourceText: string; startOffset: number; endOffset: number; sourceElementIds: string[] };
}): RequirementSourceReference {
  const transcription = input.visualTranscription;
  const hintedSpan = input.selectedSourceSpan;
  const hintedSpanValid = !transcription && hintedSpan
    && Number.isInteger(hintedSpan.startOffset) && Number.isInteger(hintedSpan.endOffset)
    && hintedSpan.startOffset >= 0 && hintedSpan.endOffset > hintedSpan.startOffset
    && hintedSpan.endOffset <= input.page.sourceText.length
    && input.page.sourceText.slice(hintedSpan.startOffset, hintedSpan.endOffset) === hintedSpan.sourceText
    && hintedSpan.sourceElementIds.length > 0
    && hintedSpan.sourceElementIds.every((id) => input.page.textBlocks.some((block) => block.id === id
      && block.startOffset <= hintedSpan.startOffset && block.endOffset >= hintedSpan.endOffset));
  const match = transcription ? null : hintedSpanValid
    ? { startOffset: hintedSpan.startOffset, endOffset: hintedSpan.endOffset, sourceText: hintedSpan.sourceText }
    : findUniqueSourceText(input.page.sourceText, input.quote);
  // A repeated native quote may be verified on this page without identifying
  // which occurrence supplied the candidate. Preserve literal page text, but
  // never invent a unique span, parser element IDs, or exact location for it.
  const nonUniqueAlignment = !transcription && !match
    ? alignExactTokenSequence(input.quote, input.page.sourceText, { requireUnique: false })
    : null;
  const pageTextWithoutUniqueLocation = nonUniqueAlignment
    ? input.page.sourceText.slice(nonUniqueAlignment.startOffset, nonUniqueAlignment.endOffset)
    : "";
  const sourceTextWithoutUniqueLocation = pageTextWithoutUniqueLocation
    && hasTechnicalAgreement(input.quote, pageTextWithoutUniqueLocation)
    ? pageTextWithoutUniqueLocation
    : "";
  let sourceCell: RequirementSourceReference["sourceCell"];
  if (input.sourceCellLocation) {
    const table = input.page.tables[0];
    const row = table?.rows[input.sourceCellLocation.rowIndex];
    const cell = row?.cells[input.sourceCellLocation.columnIndex];
    if (table && row && cell) {
      sourceCell = {
        tableId: table.id,
        rowId: row.id,
        cellId: cell.id,
        rowIndex: row.rowIndex,
        columnIndex: cell.columnIndex,
      };
    }
  }
  const exactCellText = sourceCell ? input.page.tables[0]?.rows[sourceCell.rowIndex]?.cells[sourceCell.columnIndex]?.sourceText : undefined;
  const sourceElementIds = new Set<string>();
  if (match) {
    for (const block of input.page.textBlocks) {
      if (block.startOffset < match.endOffset && block.endOffset > match.startOffset) sourceElementIds.add(block.id);
    }
  }
  if (hintedSpanValid) for (const id of hintedSpan.sourceElementIds) sourceElementIds.add(id);
  if (sourceCell) {
    sourceElementIds.add(sourceCell.tableId);
    sourceElementIds.add(sourceCell.rowId);
    sourceElementIds.add(sourceCell.cellId);
  }
  if (transcription && input.transcriptionMethod === "tesseract-ocr") {
    const ocrTranscript = input.page.ocrRegions.map((region) => region.text).join("\n");
    const ocrMatch = findUniqueTokenBoundedMatch(ocrTranscript, transcription);
    if (ocrMatch) {
      let offset = 0;
      for (const region of input.page.ocrRegions) {
        const regionEnd = offset + region.text.length;
        if (offset < ocrMatch.endOffset && regionEnd > ocrMatch.startOffset) sourceElementIds.add(region.id);
        offset = regionEnd + 1;
      }
    }
  }

  return {
    documentId: input.document.documentId,
    documentVersionId: input.document.documentVersionId,
    documentFingerprint: input.document.fingerprint,
    physicalPdfPageNumber: input.page.physicalPdfPageNumber,
    sourceText: transcription ? input.selectableTextContext ?? "" : match?.sourceText ?? exactCellText ?? sourceTextWithoutUniqueLocation,
    sourceElementIds: [...sourceElementIds],
    ...(match ? { startOffset: match.startOffset, endOffset: match.endOffset } : {}),
    ...(match ? { offsetUnit: "utf16-code-unit" as const, offsetScope: "page-source-text" as const } : {}),
    bbox: input.bbox ? { ...input.bbox } : null,
    bboxCoordinateSystem: "pdfjs-viewport-scale-1",
    extractionMethod: transcription ? input.transcriptionMethod ?? "visual-transcription" : "pdfjs-native-text",
    // Text offsets or a source-cell ID are not proof of highlight geometry.
    locationPrecision: !transcription && input.bbox && (match || sourceCell) ? "exact" : "approximate",
    ...(transcription ? { transcribedText: transcription } : {}),
    ...(transcription && input.ocrConfidence ? { ocrConfidence: input.ocrConfidence } : {}),
    ...(input.selectableTextContext ? { selectableTextContext: input.selectableTextContext } : {}),
    ...(sourceCell ? { sourceCell } : {}),
  };
}
