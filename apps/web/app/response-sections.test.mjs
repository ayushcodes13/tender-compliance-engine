import test from 'node:test';import assert from 'node:assert/strict';
import {buildResponseSections} from './response-sections.ts';
import {fixture} from './test-fixtures/response-sections.mjs';
test('source annexures and group headings become separate section metadata above body tables',()=>{
 const sheet=fixture();const before=structuredClone(sheet);const sections=buildResponseSections(sheet);
 assert.equal(sections.length,3);assert.deepEqual(sections.map(s=>[s.annexure,s.heading]),[['Annexure I','A. Optical Table'],['Annexure I','B. Isolators'],['Annexure II','A. Optical Table']]);
 assert.deepEqual(sections[0].columns.map(c=>c.header),['Specification','Description','Comply (Yes/No)','Any deviation','Remarks / Justifications']);
 assert.equal(sections[0].rows[0].values[1],'≥ 300 mm');assert.deepEqual(sections[0].titleLines,['Technical Specifications for Optical Tables']);assert.deepEqual(sheet,before);
 assert.equal(buildResponseSections(sheet,true)[0].columns.at(-1).role,'page');assert.equal(buildResponseSections(sheet,true)[0].rows[0].values.at(-1),'Page 20');
});
test('a worksheet edit is projected using original column positions and keeps every source ID',()=>{
 const sheet=fixture();sheet.rows[0].values[3]='Edited description';sheet.rows[0].sourceRequirementIds.push('continuation');const section=buildResponseSections(sheet,true)[0];
 assert.equal(section.columnIndices[1],3);assert.equal(section.rows[0].values[1],'Edited description');assert.deepEqual(section.rows[0].sourceRequirementIds,['a','continuation']);
});

test('repeated source table titles remain separate when their source heading identities differ',()=>{
 const sheet=fixture();sheet.rows[1].values[0]=sheet.rows[0].values[0];assert.equal(buildResponseSections(sheet).length,3);
});

test('explicit headings in general extraction stay outside tables without printing generated group labels',()=>{
 const sheet={columns:[{header:'Heading',role:'heading'},{header:'Tender specification',role:'requirement'},{header:'Source page',role:'page'}],rows:[
  {id:'h',sourceRequirementId:'h',sourceRequirementIds:['h'],section:true,values:['Native equipment heading','','Page 2']},
  {id:'r',sourceRequirementId:'r',sourceRequirementIds:['r'],values:['Native equipment heading','Shall retain 10 mm','Page 2']},
 ]};
 const sections=buildResponseSections(sheet);assert.equal(sections[0].heading,'Native equipment heading');assert.equal(sections[0].rows.length,1);assert.deepEqual(sections[0].columns.map(c=>c.header),['Tender specification']);
});

test('table headers retain their verified per-table source wording',()=>{
 const sheet=fixture();sheet.rows[0].sourceHeaders={2:'Parameter',3:'Required Specification'};
 assert.deepEqual(buildResponseSections(sheet)[0].columns.slice(0,2).map(c=>c.header),['Parameter','Required Specification']);
});

test('a source title already above the table is not repeated as an equipment heading',()=>{
 const sheet=fixture();sheet.rows[0].values[0]='Optical Table';sheet.rows[0].sectionHeadings=['▪ Optical Table'];
 const section=buildResponseSections(sheet)[0];
 assert.equal(section.heading,'');assert.deepEqual(section.titleLines,['▪ Optical Table']);
});
