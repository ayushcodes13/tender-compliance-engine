import test from 'node:test';
import assert from 'node:assert/strict';
import { Packer } from 'docx';
import JSZip from 'jszip';
import { fixture } from './test-fixtures/response-sections.mjs';
import { createSectionedResponseDocument, createSectionedWorkbook } from './sectioned-exports.ts';
import { buildResponseSheet, updateResponseSheetCell, addManualRequirementToSheet, promoteCandidateToSheet, removeResponseSheetRow } from './response-sheet.ts';

test('Word annexures and table headings are paragraphs outside specification tables', async () => {
  const zip = await JSZip.loadAsync(await Packer.toBuffer(createSectionedResponseDocument(fixture())));
  const xml = await zip.file('word/document.xml').async('string');
  const tables = xml.match(/<w:tbl>.*?<\/w:tbl>/gs) ?? [];
  assert.equal(tables.length, 3);
  for (const table of tables) {
    assert.ok(table.includes('Specification'));
    assert.equal(table.includes('Annexure I'), false);
    assert.equal(table.includes('Optical Table'), false);
    assert.ok(table.includes('Source page'));
  }
  assert.ok(xml.includes('Page 20'));
  assert.ok(xml.includes('Page 21'));
  assert.ok(xml.includes('Page 23'));
  assert.ok(xml.indexOf('Annexure I') < xml.indexOf('<w:tbl>'));
  assert.ok(xml.includes('Technical Specifications for Optical Tables'));
  assert.equal(xml.includes('Source tender:'), false);
  // Confirms boardroom-ready executive header fill
  assert.ok(xml.includes('1E293B'), 'Header row has 1E293B slate navy shading');
});

test('Word document supports hierarchical vertical merging for heading cells', async () => {
  const multiRow = buildResponseSheet({
    normalizedTables: true,
    requirements: [
      {
        id: 'r1',
        text: 'Spec 1',
        quote: 'Spec 1',
        page: 1,
        sourceColumnMap: [
          { header: 'Subsystem', role: 'heading' },
          { header: 'Requirement', role: 'requirement' },
        ],
        sourceCells: ['Subsystem A', 'Spec 1'],
      },
      {
        id: 'r2',
        text: 'Spec 2',
        quote: 'Spec 2',
        page: 1,
        sourceColumnMap: [
          { header: 'Subsystem', role: 'heading' },
          { header: 'Requirement', role: 'requirement' },
        ],
        sourceCells: ['Subsystem A', 'Spec 2'],
      },
    ],
  });
  const zip = await JSZip.loadAsync(await Packer.toBuffer(createSectionedResponseDocument(multiRow)));
  const xml = await zip.file('word/document.xml').async('string');
  assert.ok(xml.includes('<w:vMerge w:val="restart"/>'), 'Word table contains vMerge restart tag');
  assert.ok(xml.includes('<w:vMerge w:val="continue"/>') || xml.includes('<w:vMerge/>'), 'Word table contains vMerge continue tag');
});

test('Excel places source headings in standalone merged rows and retains specification cells', () => {
  const wb = createSectionedWorkbook(fixture());
  const sheet = wb.worksheets[0];
  const rows = [];
  sheet.eachRow((row) => rows.push(row.values));
  assert.ok(rows.some((row) => row[1] === 'Annexure I'));
  assert.ok(rows.some((row) => row[1] === 'A. Optical Table'));
  assert.ok(rows.some((row) => row[1] === 'Specification' && row[2] === 'Description'));
  assert.ok(rows.some((row) => row[2] === '≥ 300 mm'));
  assert.ok(rows.some((row) => row.includes('Source page')));
  assert.ok(rows.some((row) => row.includes('Page 20')));

  // Confirms auto-filter is configured
  assert.ok(sheet.autoFilter, 'Excel worksheet has auto-filter defined');
});

test('Excel merges consecutive rows sharing the same heading', () => {
  const multiRow = buildResponseSheet({
    normalizedTables: true,
    requirements: [
      {
        id: 'r1',
        text: 'Spec 1',
        quote: 'Spec 1',
        page: 1,
        sourceColumnMap: [
          { header: 'Subsystem', role: 'heading' },
          { header: 'Requirement', role: 'requirement' },
        ],
        sourceCells: ['Shared Subsystem', 'Spec 1'],
      },
      {
        id: 'r2',
        text: 'Spec 2',
        quote: 'Spec 2',
        page: 1,
        sourceColumnMap: [
          { header: 'Subsystem', role: 'heading' },
          { header: 'Requirement', role: 'requirement' },
        ],
        sourceCells: ['Shared Subsystem', 'Spec 2'],
      },
    ],
  });
  const wb = createSectionedWorkbook(multiRow);
  const sheet = wb.worksheets[0];
  const merges = Object.keys(sheet._merges || {});
  assert.ok(merges.length > 0, 'Excel worksheet contains merged cells for repeating headings');
});

test('Excel splits long requirement text across bounded-height rows without adding response decisions', () => {
  const longRequirement = `Tender requirement: ${'The equipment shall retain the complete technical specification and operating conditions. '.repeat(100)}`;
  const sheetData = buildResponseSheet({
    requirements: [{ id: 'long-1', text: longRequirement, quote: longRequirement, page: 4 }],
  });
  const workbook = createSectionedWorkbook(sheetData);
  const worksheet = workbook.worksheets[0];
  let requirementColumn = 0;
  let responseColumn = 0;
  worksheet.eachRow((row) => {
    const values = row.values.map((value) => String(value ?? '').toLowerCase());
    if (values.includes('tender requirement')) requirementColumn = values.indexOf('tender requirement');
    if (values.includes('compliance (yes / no)')) responseColumn = values.indexOf('compliance (yes / no)');
  });
  assert.ok(requirementColumn > 0);
  assert.ok(responseColumn > 0);

  const dataRows = [];
  worksheet.eachRow((row) => {
    const value = row.getCell(requirementColumn).value;
    if (typeof value === 'string' && value.length > 100) dataRows.push(row);
  });
  assert.ok(dataRows.length > 1, 'long source text occupies continuation rows');
  assert.equal(dataRows.map((row) => row.getCell(requirementColumn).value).join(''), sheetData.rows[0].values[1]);
  assert.ok(dataRows.every((row) => row.height <= 300));
  assert.equal(dataRows[0].getCell(responseColumn).value, '');
  assert.ok(
    Object.values(worksheet._merges || {}).some((range) => range.model?.top === dataRows[0].number && range.model?.bottom === dataRows.at(-1).number && range.model?.left === responseColumn),
    'OEM response field is vertically merged across requirement continuation rows',
  );
});

test('preserves user-edited supplier compliance and remark responses in DOCX and XLSX exports', async () => {
  const base = fixture();
  const complyColIdx = base.columns.findIndex((c) => /comply/i.test(c.header));
  const remarkColIdx = base.columns.findIndex((c) => /remark|justification/i.test(c.header));
  const edited = updateResponseSheetCell(base, base.rows[0].id, complyColIdx, 'Yes - Complied');
  const doublyEdited = updateResponseSheetCell(edited, base.rows[0].id, remarkColIdx, 'Compliant with standard warranty.');

  // DOCX
  const docxZip = await JSZip.loadAsync(await Packer.toBuffer(createSectionedResponseDocument(doublyEdited)));
  const docxXml = await docxZip.file('word/document.xml').async('string');
  assert.ok(docxXml.includes('Yes - Complied'));
  assert.ok(docxXml.includes('Compliant with standard warranty.'));

  // XLSX
  const wb = createSectionedWorkbook(doublyEdited);
  const rows = [];
  wb.worksheets[0].eachRow((r) => rows.push(r.values));
  assert.ok(rows.some((r) => r.includes('Yes - Complied')));
  assert.ok(rows.some((r) => r.includes('Compliant with standard warranty.')));
});

test('operator manual additions, candidate promotions, and row removals flow cleanly into DOCX and XLSX exports', async () => {
  const base = fixture();
  const initialRowCount = base.rows.length;

  // 1. Manually add a missing requirement (e.g. p.18 Digital readout)
  const withManual = addManualRequirementToSheet(base, {
    id: 'req-manual-p18',
    page: 18,
    heading: 'Temperature Controller',
    text: 'Digital readout: Variable temperature controller must include a digital readout with 0.1 K resolution',
    category: 'Technical',
  });
  assert.equal(withManual.rows.length, initialRowCount + 1);

  // 2. Promote a classification review candidate
  const { sheet: withPromoted } = promoteCandidateToSheet(withManual, {
    candidateId: 'cand-amc-promoted',
    page: 25,
    quote: 'Comprehensive annual maintenance contract for three years after warranty',
    heading: 'Service and Support',
  });
  assert.equal(withPromoted.rows.length, initialRowCount + 2);

  // 3. Remove an unwanted / administrative row from original base
  const rowToRemove = base.rows[0].id;
  const removedText = base.rows[0].values[3]; // '≥ 300 mm'
  const finalSheet = removeResponseSheetRow(withPromoted, rowToRemove);
  assert.equal(finalSheet.rows.length, initialRowCount + 1);

  // DOCX Export Verification
  const docxZip = await JSZip.loadAsync(await Packer.toBuffer(createSectionedResponseDocument(finalSheet)));
  const docxXml = await docxZip.file('word/document.xml').async('string');
  assert.ok(docxXml.includes('Digital readout: Variable temperature controller must include a digital readout with 0.1 K resolution'));
  assert.ok(docxXml.includes('Comprehensive annual maintenance contract for three years after warranty'));
  assert.ok(docxXml.includes('Page 18'));
  assert.ok(docxXml.includes('Page 25'));
  assert.equal(docxXml.includes(removedText), false, 'Removed row text should not appear in Word export');

  // Excel Export Verification
  const wb = createSectionedWorkbook(finalSheet);
  const excelRowValues = [];
  wb.worksheets[0].eachRow((r) => excelRowValues.push(r.values));
  const flattened = excelRowValues.flat().filter(Boolean).map(String);
  assert.ok(flattened.some((v) => v.includes('Digital readout: Variable temperature controller')));
  assert.ok(flattened.some((v) => v.includes('Comprehensive annual maintenance contract')));
  assert.ok(flattened.some((v) => v.includes('Page 18')));
  assert.ok(flattened.some((v) => v.includes('Page 25')));
  assert.equal(flattened.some((v) => v === removedText), false, 'Removed row text should not appear in Excel export');
});

