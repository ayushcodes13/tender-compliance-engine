import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createResponsePdf } from './pdf-export.ts';
import { DOMMatrix, ImageData, Path2D } from '@napi-rs/canvas';
Object.assign(globalThis,{DOMMatrix,ImageData,Path2D});
const font=readFileSync(new URL('../public/fonts/DejaVuSans.ttf',import.meta.url)).toString('base64');
const sheet={columns:[{header:'Description',role:'requirement'},{header:'Source page',role:'page'}],rows:[{id:'r1',sourceRequirementId:'r1',sourceRequirementIds:['r1'],values:[' ≥ 300 mm; ±0.1 mm; ≤ 5 µm; 10°C; 80–120 psi','Page 20']}]};

test('PDF keeps technical wording and omits source citations without changing the UI sheet',async()=>{
  const original=structuredClone(sheet);
  const pdf=createResponsePdf(sheet,'Technical requirements','synthetic.pdf',font);
  assert.deepEqual(sheet,original);
  const {getDocument}=await import('pdfjs-dist/legacy/build/pdf.mjs');
  const task=getDocument({data:new Uint8Array(pdf.output('arraybuffer')),isEvalSupported:false});
  try {
    const doc=await task.promise;const page=await doc.getPage(1);const text=(await page.getTextContent({disableNormalization:true})).items.filter(item=>'str'in item).map(item=>item.str).join(' ');
    for(const expected of ['≥ 300 mm','±0.1 mm','≤ 5 µm','10°C','80–120 psi'])assert.ok(text.includes(expected),`${expected} survived PDF export`);
    assert.equal(text.includes('Source page'),false);
    assert.equal(/\bPage \d+\b/.test(text),false);
  }finally{await task.destroy();}
});

test('unsupported glyphs stop PDF export instead of silently losing source characters',()=>{
  const unsupported={...sheet,rows:[{...sheet.rows[0],values:['中文','Page 20']}]};
  assert.throws(()=>createResponsePdf(unsupported,'Technical requirements','synthetic.pdf',font),/Download DOCX or Excel/);
});

test('keeps a source requirement together when it fits on the next PDF page',async()=>{
  const long='BEGIN REQUIREMENT '+ 'The instrument shall retain all original limits and conditions. '.repeat(18)+'END REQUIREMENT';
  const rows=Array.from({length:40},(_,i)=>({id:String(i),sourceRequirementId:String(i),sourceRequirementIds:[String(i)],values:['Short technical clause '+i,'Page 20']}));
  rows.push({id:'long',sourceRequirementId:'long',sourceRequirementIds:['long'],values:[long,'Page 21']});
  const pdf=createResponsePdf({...sheet,rows},'Technical requirements','synthetic.pdf',font);
  const {getDocument}=await import('pdfjs-dist/legacy/build/pdf.mjs');const task=getDocument({data:new Uint8Array(pdf.output('arraybuffer')),isEvalSupported:false});
  try{const document=await task.promise;let completePage=false;
    for(let i=1;i<=document.numPages;i++){const page=await document.getPage(i);const text=(await page.getTextContent({disableNormalization:true})).items.filter(item=>'str'in item).map(item=>item.str).join(' ').replace(/\s+/g,' ');assert.equal(/\bPage \d+\b/.test(text),false);if(text.includes('BEGIN REQUIREMENT')&&text.includes('END REQUIREMENT'))completePage=true;}
    assert.ok(completePage,'The complete long requirement is on one page');
  }finally{await task.destroy();}
});

test('removes a citation column in the middle without shifting the response cells',async()=>{
  const source={columns:[{header:'Description',role:'requirement'},{header:'Source page',role:'page'},{header:'Remarks',role:'response'}],rows:[{id:'r',sourceRequirementId:'r',sourceRequirementIds:['r'],values:['Keep this specification','Pages 20 and 21','Keep this remark']}]};
  const pdf=createResponsePdf(source,'Technical requirements','synthetic.pdf',font);
  const {getDocument}=await import('pdfjs-dist/legacy/build/pdf.mjs');const task=getDocument({data:new Uint8Array(pdf.output('arraybuffer')),isEvalSupported:false});
  try{const doc=await task.promise;const text=(await(await doc.getPage(1)).getTextContent()).items.filter(item=>'str'in item).map(item=>item.str).join(' ');
    assert.ok(text.includes('Keep this specification'));assert.ok(text.includes('Keep this remark'));
    assert.equal(text.includes('Source page'),false);assert.equal(text.includes('Pages 20 and 21'),false);
    assert.equal(source.rows[0].values[1],'Pages 20 and 21');
  }finally{await task.destroy();}
});

test('prints native annexure and equipment headings above the tables without generic wrappers',async()=>{
 const {fixture}=await import('./test-fixtures/response-sections.mjs');
 const pdf=createResponsePdf(fixture(),'UNWANTED GENERIC TITLE','UNWANTED-FILENAME.pdf',font);
 const {getDocument}=await import('pdfjs-dist/legacy/build/pdf.mjs');const task=getDocument({data:new Uint8Array(pdf.output('arraybuffer')),isEvalSupported:false});
 try{const document=await task.promise;let text='';for(let i=1;i<=document.numPages;i++){text+=(await(await document.getPage(i)).getTextContent()).items.filter(item=>'str'in item).map(item=>item.str).join(' ')+' ';}
 assert.ok(text.indexOf('Annexure I')<text.indexOf('Specification'));assert.ok(text.includes('Technical Specifications for Optical Tables'));assert.ok(text.includes('A. Optical Table'));assert.ok(text.includes('B. Isolators'));assert.ok(text.includes('Annexure II'));assert.equal(text.includes('UNWANTED'),false);assert.equal(text.includes('Equipment / group'),false);assert.equal(text.includes('Annexure / section'),false);
 }finally{await task.destroy();}
});
