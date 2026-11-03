import test from 'node:test';import assert from 'node:assert/strict';
import {Packer} from 'docx';import JSZip from 'jszip';
import {fixture} from './test-fixtures/response-sections.mjs';import {createSectionedResponseDocument,createSectionedWorkbook} from './sectioned-exports.ts';
test('Word annexures and table headings are paragraphs outside specification tables',async()=>{
 const zip=await JSZip.loadAsync(await Packer.toBuffer(createSectionedResponseDocument(fixture())));const xml=await zip.file('word/document.xml').async('string');
 const tables=xml.match(/<w:tbl>.*?<\/w:tbl>/gs)??[];assert.equal(tables.length,3);
 for(const table of tables){assert.ok(table.includes('Specification'));assert.equal(table.includes('Annexure I'),false);assert.equal(table.includes('Optical Table'),false);assert.equal(table.includes('Source page'),false);}
 assert.ok(xml.indexOf('Annexure I')<xml.indexOf('<w:tbl>'));assert.ok(xml.includes('Technical Specifications for Optical Tables'));assert.equal(xml.includes('Source tender:'),false);
});
test('Excel places source headings in standalone merged rows and retains specification cells',()=>{
 const sheet=createSectionedWorkbook(fixture()).worksheets[0];const rows=[];sheet.eachRow(row=>rows.push(row.values));
 assert.ok(rows.some(row=>row[1]==='Annexure I'));assert.ok(rows.some(row=>row[1]==='A. Optical Table'));assert.ok(rows.some(row=>row[1]==='Specification'&&row[2]==='Description'));assert.ok(rows.some(row=>row[2]==='≥ 300 mm'));
 assert.equal(rows.some(row=>row.includes('Source page')||row.includes('Page 20')),false);
});
