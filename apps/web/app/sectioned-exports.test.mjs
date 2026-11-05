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
    assert.equal(table.includes('Source page'), false);
  }
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
  assert.equal(rows.some((row) => row.includes('Source page') || row.includes('Page 20')), false);

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
