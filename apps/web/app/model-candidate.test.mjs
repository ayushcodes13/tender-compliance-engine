import test from 'node:test';import assert from 'node:assert/strict';
import {modelCandidateFields} from './model-candidate.ts';
test('model suggestions cannot supply internal source geometry, identity, native style, or OCR claims',()=>{
 const candidate={page:2,quote:'Accuracy ±0.1 mm',row_type:'requirement',category:'Performance',heading_prefix:'',sourceBox:{x:0,y:0,width:1,height:1},source_cells_exact:true,source_row_index:999,source_column_index:0,source_cells:['Invented'],source_column_map:[{header:'Invented',role:'specification'}],nativeHeadingPrefix:'Accuracy',visualOcr:true,visualOcrConfidence:'high',ocrWarning:false,exportGroupId:'fake'};
 const before=structuredClone(candidate);assert.deepEqual(modelCandidateFields(candidate),{page:2,quote:'Accuracy ±0.1 mm',row_type:'requirement',category:'Performance',heading_prefix:''});assert.deepEqual(candidate,before);
});
test('preserves public literal text and structure fields and safely ignores malformed records',()=>{
 const candidate={page:3,quote:'Source text',remark:'Native note',display_lines:['Source text'],heading_prefix:'Source',merge_with_next:false,continues_previous:true};assert.deepEqual(modelCandidateFields(candidate),candidate);
 for(const value of [null,[],42,'text'])assert.deepEqual(modelCandidateFields(value),{});
});
