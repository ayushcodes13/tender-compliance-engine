import test from 'node:test';import assert from 'node:assert/strict';
import {findAnnexureHeading,expandSelectedAnnexures} from './annexure-routing.ts';
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
