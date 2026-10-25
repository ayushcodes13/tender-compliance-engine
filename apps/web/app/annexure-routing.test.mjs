import test from 'node:test';import assert from 'node:assert/strict';
import {findAnnexureHeading,findTechnicalSectionHeading,expandSelectedAnnexures} from './annexure-routing.ts';
const item=(text,x,y)=>({text,box:{x,y,width:40,height:12}});
test('finds a split standalone source heading without treating a body reference as a boundary',()=>{
  assert.equal(findAnnexureHeading([item('Annexure',200,90),item('–',250,90),item('II',270,90)],800),'Annexure – II');
  assert.equal(findAnnexureHeading([item('As prescribed in Annexure-II.',40,100)],800),null);
  assert.equal(findAnnexureHeading([item('Annexure-II',40,700)],800),null);
});
test('retains annexure tails across routing batches and stops at the next source heading',()=>{
  const pages=Array.from({length:42},(_,index)=>index+1);
  assert.deepEqual(expandSelectedAnnexures([20,21,23,24,25],[20,23,27,29],pages),[20,21,22,23,24,25,26]);
  assert.deepEqual(expandSelectedAnnexures([3],[20,23,27],pages),[3]);
  assert.deepEqual(expandSelectedAnnexures([40],[20,23,27,39],pages),[39,40,41,42]);
});

test('preserves parenthesized annexure labels while rejecting body references and unbalanced punctuation',()=>{
  assert.equal(findAnnexureHeading([item('(ANNEXURE-I)',200,90)],800),'(ANNEXURE-I)');
  assert.equal(findAnnexureHeading([item('( Annexure – 123 )',200,90)],800),'( Annexure – 123 )');
  for(const text of ['See (ANNEXURE-I)','(ANNEXURE-I) requirements','(ANNEXURE-I','ANNEXURE-I)']) {
    assert.equal(findAnnexureHeading([item(text,40,100)],800),null);
  }
});

test('retains standalone technical section titles without promoting prose or treating them as annexures',()=>{
 const title='Section 4 – Technical specifications';
 assert.equal(findTechnicalSectionHeading([item('Section 4',40,90),item('– Technical specifications',100,90)],800),title);
 assert.equal(findAnnexureHeading([item(title,40,90)],800),null);
 assert.equal(findTechnicalSectionHeading([item('See Section 4 – Technical specifications',40,90)],800),null);
 assert.equal(findTechnicalSectionHeading([item(title,40,700)],800),null);
});

test('retains literal source title lines below an annexure and above the table',async()=>{
 const {sourceAnnexureTitleLines}=await import('./annexure-routing.ts');
 const items=[item('Institute header',10,10),item('Annexure I',10,60),item('Technical Specifications',10,80),item('for Optical Tables',10,100),item('A. Optical Table',10,130),item('Invented title',10,110)];
 assert.deepEqual(sourceAnnexureTitleLines(items,'Annexure I',125,'Institute header Annexure I Technical Specifications for Optical Tables A. Optical Table'),['Technical Specifications','for Optical Tables']);
});


test('a standalone technical title can start a table below an invitation on the same page',()=>{
 assert.equal(findTechnicalSectionHeading([item('Invitation for Tender Offers',40,100),item('TECHNICAL SPECIFICATION',40,350)],800),'TECHNICAL SPECIFICATION');
 assert.equal(findTechnicalSectionHeading([item('See TECHNICAL SPECIFICATION for details',40,350)],800),null);
 assert.equal(findTechnicalSectionHeading([item('Technical Specification',40,730)],800),null);
});

test('top-aligned response headers do not become source title lines above the table',async()=>{
 const {sourceTableTextTop,sourceAnnexureTitleLines}=await import('./annexure-routing.ts');
 const top=sourceTableTextTop([{bbox:{y:100},cellBoxes:[{y:100},{y:80}]}]);
 assert.equal(top,80);assert.equal(sourceTableTextTop([]),0);
 assert.deepEqual(sourceAnnexureTitleLines([item('Annexure I',40,20),item('Technical Specification',40,40),item('Compliance',400,80),item('Y/N',400,95),item('Technical Parameters',40,100)],'Annexure I',top,'Annexure I Technical Specification Compliance Y/N Technical Parameters'),['Technical Specification']);
});
