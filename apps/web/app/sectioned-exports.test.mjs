import test from 'node:test';
import assert from 'node:assert/strict';
import { Packer } from 'docx';
import JSZip from 'jszip';
import { fixture } from './test-fixtures/response-sections.mjs';
import { createSectionedResponseDocument, createSectionedWorkbook } from './sectioned-exports.ts';
import { buildResponseSheet } from './response-sheet.ts';

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
