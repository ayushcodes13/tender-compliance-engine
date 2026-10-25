import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createResponsePdf } from './pdf-export.ts';
import { DOMMatrix, ImageData, Path2D } from '@napi-rs/canvas';
Object.assign(globalThis,{DOMMatrix,ImageData,Path2D});
const font=readFileSync(new URL('../public/fonts/DejaVuSans.ttf',import.meta.url)).toString('base64');
const sheet={columns:[{header:'Description',role:'requirement'},{header:'Source page',role:'page'}],rows:[{id:'r1',sourceRequirementId:'r1',sourceRequirementIds:['r1'],values:[' ≥ 300 mm; ±0.1 mm; ≤ 5 µm; 10°C; 80–120 psi','Page 20']}]};

test('PDF round trip retains comparison signs, precision, units, and source page',async()=>{
  const pdf=createResponsePdf(sheet,'Technical requirements','synthetic.pdf',font);
  const {getDocument}=await import('pdfjs-dist/legacy/build/pdf.mjs');
  const task=getDocument({data:new Uint8Array(pdf.output('arraybuffer')),isEvalSupported:false});
  try {
    const doc=await task.promise;const page=await doc.getPage(1);const text=(await page.getTextContent({disableNormalization:true})).items.filter(item=>'str'in item).map(item=>item.str).join(' ');
    for(const expected of ['≥ 300 mm','±0.1 mm','≤ 5 µm','10°C','80–120 psi','Page 20'])assert.ok(text.includes(expected),`${expected} survived PDF export`);
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
    for(let i=1;i<=document.numPages;i++){const page=await document.getPage(i);const text=(await page.getTextContent({disableNormalization:true})).items.filter(item=>'str'in item).map(item=>item.str).join(' ').replace(/\s+/g,' ');if(text.includes('BEGIN REQUIREMENT')&&text.includes('END REQUIREMENT'))completePage=true;}
    assert.ok(completePage,'The complete long requirement is on one page');
  }finally{await task.destroy();}
});
