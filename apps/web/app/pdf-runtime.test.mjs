import test from 'node:test';import assert from 'node:assert/strict';
import {jsPDF} from 'jspdf';import {createCanvas,DOMMatrix,ImageData,Path2D} from '@napi-rs/canvas';
import {PDF_FONT_OPTIONS} from './pdf-runtime.ts';
Object.assign(globalThis,{DOMMatrix,ImageData,Path2D});

test('renders standard PDF fonts without relying on host-installed fonts',async()=>{
  const source=new jsPDF({unit:'pt'});source.setFont('times');source.setFontSize(20);source.text('Technical requirements 300 mm',40,60);
  const {getDocument}=await import('pdfjs-dist/legacy/build/pdf.mjs');
  const task=getDocument({data:new Uint8Array(source.output('arraybuffer')),isEvalSupported:false,...PDF_FONT_OPTIONS});
  try{
    const document=await task.promise;const page=await document.getPage(1);const viewport=page.getViewport({scale:1});
    const canvas=createCanvas(Math.ceil(viewport.width),Math.ceil(viewport.height));const context=canvas.getContext('2d');
    await page.render({canvasContext:context,viewport}).promise;
    const pixels=context.getImageData(35,35,300,35).data;
    let dark=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i]<150&&pixels[i+1]<150&&pixels[i+2]<150)dark++;
    assert.ok(dark>300,'Rendered the source text rather than a blank page');
  }finally{await task.destroy();}
});
