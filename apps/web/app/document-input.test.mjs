import test from 'node:test';
import assert from 'node:assert/strict';
import { combinePageTranscripts, useComplianceSheetLayout, buildExtractionBatches } from './document-input.ts';
import { buildRoutingBatches } from './page-routing.ts';
import { sourceCandidateKey } from './visual-table.ts';

test('a selectable header does not hide the OCR body from routing', () => {
  const native = 'Tender 17';
  const ocr = 'Technical specifications\nCryostat shall retain helium for 90 days.';
  const text = combinePageTranscripts(native, ocr);
  const batches = buildRoutingBatches([{page: 1, rawText: native, text, routingText: text}]);
  assert.match(batches[0].input, /Cryostat shall retain helium for 90 days/);
  assert.equal(native, 'Tender 17');
});

test('mixed narrative and schedule sections use a general response sheet', () => {
  const schedule = {title:'Schedule',start_page:2,end_page:3,section_type:'compliance_schedule',reason:'Headers'};
  const prose = {title:'Safety',start_page:4,end_page:4,section_type:'technical_requirements',reason:'Clauses'};
  assert.equal(useComplianceSheetLayout([schedule], [2,3]),true);
  assert.equal(useComplianceSheetLayout([schedule,prose], [2,3,4]),false);
  assert.equal(useComplianceSheetLayout([], []),false);
});

test('bounded batches preserve every page and overlap long-page windows', () => {
  const pages = Array.from({length:9}, (_,i)=>({page:i+1,text:`Page ${i+1} `+'spec '.repeat(100)}));
  pages[4].text = 'unique-prefix '+ 'long clause '.repeat(3000)+' unique-suffix';
  const batches = buildExtractionBatches(pages, 2000, 2);
  assert.deepEqual([...new Set(batches.flatMap(b=>b.pageNumbers))],[1,2,3,4,5,6,7,8,9]);
  assert.ok(batches.every(b=>b.input.length <=2000 && b.pageNumbers.length<=2));
  assert.match(batches.map(b=>b.input).join('\n'), /unique-prefix/);
  assert.match(batches.map(b=>b.input).join('\n'), /unique-suffix/);
  const longPage = batches.filter(b=>b.pageNumbers.includes(5));
  assert.ok(longPage.length>1);
  assert.ok(longPage[0].input.endsWith(longPage[1].input.split('\n').slice(1).join('\n').slice(0,400)));
  assert.throws(()=>buildExtractionBatches(pages,0,0));
});

test('identical table cell text remains distinct at distinct source row locations', () => {
  assert.notEqual(sourceCandidateKey(1,'Shall include cooling',['Shall include cooling'],0),sourceCandidateKey(1,'Shall include cooling',['Shall include cooling'],1));
  assert.equal(sourceCandidateKey(1,'Same',undefined),sourceCandidateKey(1,'Same',undefined));
});
