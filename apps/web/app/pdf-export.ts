import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { ResponseSheet } from './response-sheet.ts';
import { buildResponseSections } from './response-sections.ts';

function getPdfColumnWeight(column: { header: string; role?: string }): number {
  if (column.role === 'requirement') return 4.0;
  if (column.role === 'review') return 1.5;
  const h = column.header.toLowerCase();
  if (h.includes('remark') || h.includes('justification') || h.includes('deviation')) return 2.2;
  if (h.includes('comply') || h.includes('compliance')) return 1.4;
  if (column.role === 'heading') return 1.8;
  if (column.role === 'source' || h.includes('sl.')) return 0.8;
  return 1.2;
}

/** Native source headings sit above specification tables; UI provenance stays in the UI. */
export function createResponsePdf(sheet: ResponseSheet, _title: string, _filename: string, fontBase64: string): jsPDF {
  const sections = buildResponseSections(sheet);
  const columnCount = Math.max(0, ...sections.map((section) => section.columns.length));
  const pdf = new jsPDF({
    orientation: columnCount > 4 ? 'landscape' : 'portrait',
    unit: 'pt',
    format: columnCount > 6 ? 'a3' : 'a4',
  });
  pdf.addFileToVFS('DejaVuSans.ttf', fontBase64);
  pdf.addFont('DejaVuSans.ttf', 'TenderUnicode', 'normal');
  pdf.setFont('TenderUnicode', 'normal');

  const metadata = pdf.getFont().metadata as unknown as { characterToGlyph?: (codePoint: number) => number };
  // PDF text extraction can expose visually ordinary bullets as private-use
  // glyphs depending on the source font. Normalize the two encountered forms
  // before checking/rendering with the embedded Unicode font.
  const visible = (value: string) => value.replace(/[\uF0A7\uF0B7]/g, '•');
  const texts = sections.flatMap((section) => [
    section.annexure,
    ...section.titleLines,
    section.heading,
    ...section.columns.map((column) => column.header),
    ...section.rows.flatMap((row) => row.values),
  ]);

  for (const text of texts.map(visible)) {
    for (const character of text) {
      if (!/\s/.test(character) && !metadata.characterToGlyph?.(character.codePointAt(0)!)) {
        throw new Error(
          'The PDF font cannot render one or more source characters. Download DOCX or Excel to preserve the wording.',
        );
      }
    }
  }

  const width = pdf.internal.pageSize.getWidth() - 72;
  const bottom = pdf.internal.pageSize.getHeight() - 36;
  let y = 36;
  let previousAnnexure = '';

  const heading = (text: string, size: number) => {
    if (!text) return;
    pdf.setFont('TenderUnicode', 'normal');
    pdf.setFontSize(size);
    const lines = pdf.splitTextToSize(visible(text), width) as string[];
    const height = lines.length * size * 1.25;
    if (y + height > bottom) {
      pdf.addPage();
      y = 36;
    }
    pdf.text(lines, 36, y + size);
    y += height + 8;
  };

  for (const section of sections) {
    if (section.annexure !== previousAnnexure) {
      if (previousAnnexure) {
        pdf.addPage();
        y = 36;
      }
      heading(section.annexure, 14);
      for (const line of section.titleLines) heading(line, 11);
      previousAnnexure = section.annexure;
    }
    if (y > bottom - 95) {
      pdf.addPage();
      y = 36;
    }
    heading(section.heading, 12);

    const weights = section.columns.map(getPdfColumnWeight);
    const total = weights.reduce((sum, weight) => sum + weight, 0) || 1;

    autoTable(pdf, {
      startY: y,
      head: [section.columns.map((column) => visible(column.header))],
      body: section.rows.map((row) => row.values.map(visible)),
      styles: {
        font: 'TenderUnicode',
        fontStyle: 'normal',
        fontSize: 8.5,
        cellPadding: 5.5,
        overflow: 'linebreak',
        valign: 'top',
        lineColor: [203, 213, 225],
        lineWidth: 0.5,
      },
      columnStyles: Object.fromEntries(
        weights.map((weight, index) => [index, { cellWidth: (width * weight) / total }]),
      ),
      headStyles: {
        fillColor: [30, 41, 59],
        textColor: [255, 255, 255],
        fontStyle: 'normal',
        fontSize: 9,
        lineColor: [203, 213, 225],
        lineWidth: 0.5,
      },
      alternateRowStyles: {
        fillColor: [248, 250, 252],
      },
      theme: 'grid',
      margin: { left: 36, right: 36, top: 75, bottom: 36 },
      showHead: 'everyPage',
      rowPageBreak: 'avoid',
      didDrawPage(data) {
        if (data.pageNumber > 1) {
          pdf.setFont('TenderUnicode', 'normal');
          pdf.setFontSize(11);
          if (section.annexure) pdf.text(visible(section.annexure), 36, 30);
          pdf.setFontSize(10);
          if (section.heading) pdf.text(visible(section.heading), 36, 49, { maxWidth: width });
        }
      },
    });
    y = (pdf as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 18;
  }
  return pdf;
}
