import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { ResponseSheet } from './response-sheet.ts';
import { responseHeadingMergeKeys } from './response-sheet.ts';
import { verticalMergeAt } from './compliance-format.ts';

/** Embedded Unicode font preserves comparison signs, units and source punctuation. */
export function createResponsePdf(sheet: ResponseSheet, title: string, filename: string, fontBase64: string): jsPDF {
  // Keep provenance in the review model/UI; the printable PDF omits citations.
  const printableIndices = sheet.columns.flatMap((column, index) => column.role === 'page' ? [] : [index]);
  sheet = {
    columns: printableIndices.map(index => sheet.columns[index]),
    rows: sheet.rows.map(row => ({...row, values: printableIndices.map(index => row.values[index] ?? '')})),
  };
  const pdf = new jsPDF({orientation:sheet.columns.length > 4 ? 'landscape':'portrait',unit:'pt',format:sheet.columns.length > 6 ? 'a3':'a4'});
  pdf.addFileToVFS('DejaVuSans.ttf',fontBase64);
  pdf.addFont('DejaVuSans.ttf','TenderUnicode','normal');
  pdf.setFont('TenderUnicode','normal');
  const metadata = pdf.getFont().metadata as unknown as { characterToGlyph?: (codePoint: number) => number };
  // PDFs using Symbol commonly expose this bullet as a private-use code point.
  // Render its visible bullet; leave the original evidence and worksheet text unchanged.
  const visibleText = (value: string) => value.replace(/\uF0B7/g, "•");
  const texts=[title,filename,...sheet.columns.map(column=>column.header),...sheet.rows.flatMap(row=>row.values)];
  for(const text of texts.map(visibleText)) for(const character of text) {
    if(/\s/.test(character)) continue;
    if(!metadata.characterToGlyph?.(character.codePointAt(0)!)) {
      throw new Error('The PDF font cannot render one or more source characters. Download DOCX or Excel to preserve the wording.');
    }
  }
  pdf.setFontSize(15);
  pdf.text(visibleText(title),36,34,{maxWidth:pdf.internal.pageSize.getWidth()-72});
  pdf.setFontSize(8);
  pdf.text(`Source tender: ${filename} · ${sheet.rows.length} worksheet rows`,36,49);
  const headingColumn=sheet.columns.findIndex(column=>column.role==='heading');
  const headingValues=responseHeadingMergeKeys(sheet);
  const weights = sheet.columns.map(column => column.role === 'requirement' ? 3.8 : column.role === 'heading' ? 1.5 : 1);
  const totalWeight = weights.reduce((sum,weight)=>sum+weight,0);
  const usableWidth = pdf.internal.pageSize.getWidth()-72;
  autoTable(pdf,{
    startY:60,
    head:[sheet.columns.map(column=>visibleText(column.header))],
    body:sheet.rows.map((row,index)=>row.values.map((value,column)=>column===headingColumn&&verticalMergeAt(headingValues,index)==='continue'?'':visibleText(value))),
    styles:{font:'TenderUnicode',fontStyle:'normal',fontSize:8,cellPadding:4,overflow:'linebreak',valign:'top'},
    columnStyles:Object.fromEntries(weights.map((weight,index)=>[index,{cellWidth:usableWidth*weight/totalWeight}])),
    headStyles:{fillColor:[36,79,187],textColor:255,fontStyle:'normal'},
    alternateRowStyles:{fillColor:[247,249,252]},
    margin:{left:36,right:36,top:60,bottom:32},showHead:'everyPage',rowPageBreak:'avoid',
    didDrawPage(data){
      pdf.setFont('TenderUnicode','normal');
      if(data.pageNumber>1){pdf.setFontSize(11);pdf.text(`${title} (continued)`,36,34,{maxWidth:pdf.internal.pageSize.getWidth()-72});pdf.setFontSize(7);pdf.text(`Source tender: ${filename}`,36,49);}
    },
  });
  return pdf;
}
