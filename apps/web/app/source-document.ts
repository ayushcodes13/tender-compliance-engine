import { createHash } from "node:crypto";

export type SourceBox = { x: number; y: number; width: number; height: number };

export type SourceTextBlock = {
  id: string;
  text: string;
  startOffset: number;
  endOffset: number;
  bbox: SourceBox | null;
  extractionMethod: "pdfjs-native-text";
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

export type SourcePageModel = {
  id: string;
  physicalPdfPageNumber: number;
  printedPageNumber?: number;
  width: number;
  height: number;
  coordinateSystem: "pdfjs-viewport-scale-1";
  sourceText: string;
  extractionMethod: "pdfjs-native-text" | "no-selectable-text";
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

export type SourceCellLocation = { rowIndex: number; columnIndex: number };

export type RequirementSourceReference = {
  documentId: string;
  documentVersionId: string;
  documentFingerprint: string;
  physicalPdfPageNumber: number;
  sourceText: string;
  startOffset?: number;
  endOffset?: number;
  offsetUnit?: "utf16-code-unit";
  offsetScope?: "page-source-text";
  bbox: SourceBox | null;
  bboxCoordinateSystem: "pdfjs-viewport-scale-1";
  extractionMethod: "pdfjs-native-text" | "visual-transcription";
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

export function buildSourcePageModel(input: {
  documentId: string;
  physicalPdfPageNumber: number;
  width: number;
  height: number;
  sourceText: string;
  positionedItems: PositionedSourceItem[];
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

  return {
    id: pageId,
    physicalPdfPageNumber: input.physicalPdfPageNumber,
    width: input.width,
    height: input.height,
    coordinateSystem: "pdfjs-viewport-scale-1",
    sourceText: input.sourceText,
    extractionMethod: input.sourceText.trim() ? "pdfjs-native-text" : "no-selectable-text",
    textBlocks,
    tables,
    warnings: input.sourceText.trim() ? [] : ["No selectable text was found on this page."],
  };
}

export function findUniqueSourceText(rawText: string, quote: string): { startOffset: number; endOffset: number; sourceText: string } | null {
  const target = quote.replace(/\s+/g, " ").trim();
  if (!target) return null;

  let searchable = "";
  const rawOffsets: number[] = [];
  let inWhitespace = false;
  for (let index = 0; index < rawText.length; index += 1) {
    const char = rawText[index];
    if (/\s/.test(char)) {
      if (!inWhitespace) {
        searchable += " ";
        rawOffsets.push(index);
      }
      inWhitespace = true;
    } else {
      searchable += char;
      rawOffsets.push(index);
      inWhitespace = false;
    }
  }
  const start = searchable.indexOf(target);
  if (start < 0 || searchable.indexOf(target, start + target.length) >= 0) return null;
  const startOffset = rawOffsets[start];
  const endOffset = rawOffsets[start + target.length - 1] + 1;
  return { startOffset, endOffset, sourceText: rawText.slice(startOffset, endOffset) };
}

export function buildRequirementSourceReference(input: {
  document: SourceDocumentModel;
  page: SourcePageModel;
  quote: string;
  bbox: SourceBox | null;
  visualTranscription?: string;
  ocrConfidence?: "high" | "medium" | "low";
  selectableTextContext?: string;
  sourceCellLocation?: SourceCellLocation;
}): RequirementSourceReference {
  const transcription = input.visualTranscription;
  const match = transcription ? null : findUniqueSourceText(input.page.sourceText, input.quote);
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

  return {
    documentId: input.document.documentId,
    documentVersionId: input.document.documentVersionId,
    documentFingerprint: input.document.fingerprint,
    physicalPdfPageNumber: input.page.physicalPdfPageNumber,
    sourceText: transcription ? input.selectableTextContext ?? "" : match?.sourceText ?? exactCellText ?? "",
    ...(match ? { startOffset: match.startOffset, endOffset: match.endOffset } : {}),
    ...(match ? { offsetUnit: "utf16-code-unit" as const, offsetScope: "page-source-text" as const } : {}),
    bbox: input.bbox ? { ...input.bbox } : null,
    bboxCoordinateSystem: "pdfjs-viewport-scale-1",
    extractionMethod: transcription ? "visual-transcription" : "pdfjs-native-text",
    locationPrecision: transcription ? "approximate" : match || sourceCell ? "exact" : "approximate",
    ...(transcription ? { transcribedText: transcription } : {}),
    ...(transcription && input.ocrConfidence ? { ocrConfidence: input.ocrConfidence } : {}),
    ...(input.selectableTextContext ? { selectableTextContext: input.selectableTextContext } : {}),
    ...(sourceCell ? { sourceCell } : {}),
  };
}
