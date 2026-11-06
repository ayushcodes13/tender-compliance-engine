import {
  BorderStyle,
  Document,
  HeadingLevel,
  HeightRule,
  Packer,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  VerticalMergeType,
  WidthType,
} from 'docx';
import ExcelJS from 'exceljs';
import type { ResponseSheet } from './response-sheet.ts';
import { buildResponseSections } from './response-sections.ts';
import { verticalMergeAt } from './compliance-format.ts';

function isMergeableColumn(column: { header: string; role?: string }): boolean {
  if (column.role === 'heading') return true;
  if (
    column.role === 'source' &&
    !column.header.toLowerCase().includes('sl.') &&
    !column.header.toLowerCase().includes('serial')
  ) {
    return true;
  }
  return false;
}

function getColumnWeight(column: { header: string; role?: string }): number {
  if (column.role === 'requirement') return 4.0;
  const h = column.header.toLowerCase();
  if (h.includes('remark') || h.includes('justification') || h.includes('deviation')) return 2.2;
  if (h.includes('comply') || h.includes('compliance')) return 1.4;
  if (column.role === 'heading') return 1.8;
  if (column.role === 'source' || h.includes('sl.')) return 0.8;
  return 1.2;
}

function getExcelColumnWidth(column: { header: string; role?: string }): number {
  if (column.role === 'requirement') return 72;
  const h = column.header.toLowerCase();
  if (h.includes('remark') || h.includes('justification') || h.includes('deviation')) return 36;
  if (h.includes('comply') || h.includes('compliance')) return 20;
  if (column.role === 'heading') return 28;
  if (column.role === 'source' || h.includes('sl.')) return 10;
  return 24;
}

const cellBorders = {
  top: { style: BorderStyle.SINGLE, size: 4, color: 'CBD5E1' },
  bottom: { style: BorderStyle.SINGLE, size: 4, color: 'CBD5E1' },
  left: { style: BorderStyle.SINGLE, size: 4, color: 'CBD5E1' },
  right: { style: BorderStyle.SINGLE, size: 4, color: 'CBD5E1' },
};

export function createSectionedResponseDocument(sheet: ResponseSheet): Document {
  const content: Array<Paragraph | Table> = [];
  let previousAnnexure = '';

  for (const section of buildResponseSections(sheet)) {
    if (section.annexure !== previousAnnexure) {
      content.push(
        new Paragraph({
          text: section.annexure,
          heading: HeadingLevel.HEADING_1,
          pageBreakBefore: Boolean(previousAnnexure),
          keepNext: true,
        }),
      );
      for (const line of section.titleLines) {
        content.push(new Paragraph({ text: line, keepNext: true, spacing: { after: 100 } }));
      }
      previousAnnexure = section.annexure;
    }
    if (section.heading) {
      content.push(new Paragraph({ text: section.heading, heading: HeadingLevel.HEADING_2, keepNext: true }));
    }

    const weights = section.columns.map(getColumnWeight);
    const sum = weights.reduce((a, b) => a + b, 0) || 1;
    const colWidths = weights.map((weight) => Math.floor((15440 * weight) / sum));

    // Header row
    const headerRow = new TableRow({
      tableHeader: true,
      cantSplit: true,
      children: section.columns.map((column, colIdx) =>
        new TableCell({
          width: { size: colWidths[colIdx], type: WidthType.DXA },
          shading: { fill: '1E293B', type: ShadingType.SOLID },
          borders: cellBorders,
          margins: { top: 120, bottom: 120, left: 140, right: 140 },
          children: [
            new Paragraph({
              children: [new TextRun({ text: column.header, bold: true, size: 19, color: 'FFFFFF' })],
            }),
          ],
        }),
      ),
    });

    // Data rows with hierarchical vertical cell merge
    const dataRows = section.rows.map((row, rowIdx) => {
      const cells = row.values.map((value, colIdx) => {
        const column = section.columns[colIdx];
        const isHeadingCol = isMergeableColumn(column);
        const colValues = section.rows.map((r) => r.values[colIdx]);
        const merge = isHeadingCol ? verticalMergeAt(colValues, rowIdx) : undefined;

        let verticalMerge: (typeof VerticalMergeType)[keyof typeof VerticalMergeType] | undefined;
        if (merge === 'restart') {
          verticalMerge = VerticalMergeType.RESTART;
        } else if (merge === 'continue') {
          verticalMerge = VerticalMergeType.CONTINUE;
        }

        return new TableCell({
          width: { size: colWidths[colIdx], type: WidthType.DXA },
          verticalMerge,
          borders: cellBorders,
          margins: { top: 100, bottom: 100, left: 130, right: 130 },
          children: [
            new Paragraph({
              children: [
                new TextRun({
                  text: value.replace(/\uF0B7/g, '•'),
                  bold: isHeadingCol && merge === 'restart',
                  size: 19,
                  color: '0F172A',
                }),
              ],
            }),
          ],
        });
      });

      return new TableRow({ cantSplit: true, children: cells });
    });

    content.push(
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        columnWidths: colWidths,
        rows: [headerRow, ...dataRows],
      }),
    );
    content.push(new Paragraph({ text: '', spacing: { after: 120 } }));
  }

  return new Document({
    styles: {
      default: { document: { run: { font: 'Calibri', size: 19, color: '0F172A' } } },
      paragraphStyles: [
        {
          id: 'Heading1',
          name: 'Heading 1',
          basedOn: 'Normal',
          next: 'Normal',
          run: { bold: true, size: 28, color: '0F172A' },
          paragraph: { spacing: { before: 140, after: 160 } },
        },
        {
          id: 'Heading2',
          name: 'Heading 2',
          basedOn: 'Normal',
          next: 'Normal',
          run: { bold: true, size: 23, color: '1E293B' },
          paragraph: { spacing: { before: 180, after: 120 } },
        },
      ],
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: 16840, height: 11910 },
            margin: { top: 720, right: 720, bottom: 720, left: 720 },
          },
        },
        children: content,
      },
    ],
  });
}

export async function createSectionedDocxBlob(sheet: ResponseSheet): Promise<Blob> {
  return Packer.toBlob(createSectionedResponseDocument(sheet));
}

const excelThinBorder: Partial<ExcelJS.Borders> = {
  top: { style: 'thin', color: { argb: 'FFCBD5E1' } },
  bottom: { style: 'thin', color: { argb: 'FFCBD5E1' } },
  left: { style: 'thin', color: { argb: 'FFCBD5E1' } },
  right: { style: 'thin', color: { argb: 'FFCBD5E1' } },
};

const MAX_EXCEL_DATA_ROW_HEIGHT = 300;
const EXCEL_LINE_HEIGHT = 14;
const EXCEL_ROW_PADDING = 8;
const EXCEL_MAX_ESTIMATED_LINES = Math.floor((MAX_EXCEL_DATA_ROW_HEIGHT - EXCEL_ROW_PADDING) / EXCEL_LINE_HEIGHT);

function splitCellForExcel(value: string, width: number): string[] {
  const pieces: string[] = [];
  let current = '';
  let lineCount = 0;

  // Keep every source character, including explicit newlines and spaces.
  for (const match of value.matchAll(/[^\n]*\n|[^\n]+$|\n/g)) {
    const segment = match[0];
    const segmentLines = Math.max(1, Math.ceil(segment.replace(/\n$/, '').length / width));
    if (current && lineCount + segmentLines > EXCEL_MAX_ESTIMATED_LINES) {
      pieces.push(current);
      current = '';
      lineCount = 0;
    }
    if (segmentLines > EXCEL_MAX_ESTIMATED_LINES) {
      const size = width * EXCEL_MAX_ESTIMATED_LINES;
      for (let offset = 0; offset < segment.length; offset += size) pieces.push(segment.slice(offset, offset + size));
    } else {
      current += segment;
      lineCount += segmentLines;
    }
  }
  if (current || pieces.length === 0) pieces.push(current);
  return pieces;
}

export function createSectionedWorkbook(sheet: ResponseSheet): ExcelJS.Workbook {
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Technical response');
  let previousAnnexure = '';
  let firstHeaderRowNumber: number | null = null;
  let lastDataRowNumber = 1;
  let maxColumnCount = 1;

  for (const section of buildResponseSections(sheet)) {
    const count = section.columns.length;
    if (count > maxColumnCount) maxColumnCount = count;

    const addHeading = (text: string, size: number) => {
      if (!text) return;
      const row = worksheet.addRow([text]);
      if (count > 1) worksheet.mergeCells(row.number, 1, row.number, count);
      row.font = { bold: true, size, name: 'Arial', color: { argb: 'FF0F172A' } };
      row.alignment = { wrapText: true, vertical: 'top' };
      row.height = 24;
    };

    if (section.annexure !== previousAnnexure) {
      addHeading(section.annexure, 14);
      for (const line of section.titleLines) addHeading(line, 11);
      previousAnnexure = section.annexure;
    }
    addHeading(section.heading, 12);

    // Table Header row
    const header = worksheet.addRow(section.columns.map((column) => column.header));
    header.font = { bold: true, name: 'Arial', size: 10, color: { argb: 'FFFFFFFF' } };
    header.height = 26;
    if (firstHeaderRowNumber === null) firstHeaderRowNumber = header.number;

    header.eachCell((cell) => {
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF1E293B' } };
      cell.alignment = { wrapText: true, vertical: 'middle', horizontal: 'left' };
      cell.border = excelThinBorder;
    });

    const startDataRowNumber = worksheet.rowCount + 1;
    const physicalRows: Array<{ values: string[] }> = [];
    const responseSpans: Array<{ start: number; end: number }> = [];

    for (const [logicalIndex, row] of section.rows.entries()) {
      const chunks = row.values.map((value, index) => splitCellForExcel(
        value.replace(/\uF0B7/g, '•'),
        section.columns[index]?.role === 'requirement' ? 70 : getExcelColumnWidth(section.columns[index] ?? { header: '' }),
      ));
      const physicalCount = Math.max(1, ...chunks.map((parts) => parts.length));
      const physicalStart = physicalRows.length;
      for (let part = 0; part < physicalCount; part++) {
        physicalRows.push({
          values: chunks.map((parts, index) => {
            const role = section.columns[index]?.role;
            if (part > 0 && role === 'response') return '';
            if (role === 'response') return parts.join('');
            if (role === 'heading') return parts.join('');
            return parts[part] ?? '';
          }),
        });
      }
      if (physicalCount > 1) responseSpans.push({ start: startDataRowNumber + physicalStart, end: startDataRowNumber + physicalRows.length - 1 });
    }

    for (const { values } of physicalRows) {
      const added = worksheet.addRow(values);
      added.font = { name: 'Arial', size: 10, color: { argb: 'FF1E293B' } };

      const computedHeight = Math.max(
        22,
        ...values.map(
          (value, index) =>
            value
              .split(/\r?\n/)
              .reduce(
                (sum, line) =>
                  sum + Math.max(1, Math.ceil(line.length / (section.columns[index]?.role === 'requirement' ? 70 : 26))),
                0,
              ) *
              14 +
            8,
        ),
      );
      added.height = Math.min(MAX_EXCEL_DATA_ROW_HEIGHT, computedHeight);

      added.eachCell({ includeEmpty: true }, (cell) => {
        cell.alignment = { wrapText: true, vertical: 'top' };
        cell.border = excelThinBorder;
      });
    }

    lastDataRowNumber = worksheet.rowCount;

    // Continuation rows extend the same answer opportunity for this requirement.
    for (const span of responseSpans) {
      section.columns.forEach((column, colIdx) => {
        if (column.role === 'response') {
          worksheet.mergeCells(span.start, colIdx + 1, span.end, colIdx + 1);
          worksheet.getCell(span.start, colIdx + 1).alignment = { wrapText: true, vertical: 'top' };
        }
      });
    }

    // Apply vertical hierarchical cell merges for heading columns
    section.columns.forEach((column, colIdx) => {
      if (isMergeableColumn(column)) {
        const colValues = physicalRows.map((r) => r.values[colIdx]);
        let r = 0;
        while (r < colValues.length) {
          if (verticalMergeAt(colValues, r) === 'restart') {
            let span = 1;
            while (r + span < colValues.length && colValues[r + span] === colValues[r]) {
              span++;
            }
            if (span > 1) {
              const startRow = startDataRowNumber + r;
              const endRow = startDataRowNumber + r + span - 1;
              const colNumber = colIdx + 1;
              worksheet.mergeCells(startRow, colNumber, endRow, colNumber);
              const mergedCell = worksheet.getCell(startRow, colNumber);
              mergedCell.alignment = { wrapText: true, vertical: 'top' };
              mergedCell.font = { bold: true, name: 'Arial', size: 10, color: { argb: 'FF0F172A' } };
            }
            r += span;
          } else {
            r++;
          }
        }
      }
    });

    worksheet.addRow([]);

    section.columns.forEach((column, index) => {
      worksheet.getColumn(index + 1).width = getExcelColumnWidth(column);
    });
  }

  // Set worksheet auto-filter across the main technical response table
  if (firstHeaderRowNumber !== null && lastDataRowNumber >= firstHeaderRowNumber) {
    worksheet.autoFilter = {
      from: { row: firstHeaderRowNumber, column: 1 },
      to: { row: lastDataRowNumber, column: maxColumnCount },
    };
  }

  worksheet.pageSetup = { orientation: 'landscape', fitToPage: true, fitToWidth: 1, fitToHeight: 0 };
  return workbook;
}
