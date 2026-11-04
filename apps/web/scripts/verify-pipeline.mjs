// Deterministic contract test: real PDF parsing/API/SSE/source validation/sheet edits,
// scripted provider responses. This does not measure the live model's recall.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import http from 'node:http';
import { once } from 'node:events';
import { spawn } from 'node:child_process';
import { jsPDF } from 'jspdf';
import { buildResponseSections } from '../app/response-sections.ts';
import { buildResponseSheet, updateResponseSheetCell, removeResponseSheetRow } from '../app/response-sheet.ts';
import { consumeAnalysisStream } from '../app/analysis-events.ts';

const quotes = [
  'Cryostat shall retain helium for 90 days.',
  'Vacuum shall remain below 0.000001 mbar.',
  'The bidder shall supply a 24 V controller.',
  'Firmware must support the OPC UA protocol.',
  'Ferromagnetic stainless steel.',
];
const recovery = 'Surface flatness shall be within 0.1 mm over 1 m square.';
const outsideTable = 'Service support shall remain available for 10 years.';
let scenario = "prose";
let extractionCalls = 0;
let routeCalls = 0;
const provider = http.createServer(async (request, response) => {
  try {
    let raw = '';
    for await (const chunk of request) raw += chunk;
    const body = JSON.parse(raw);
    const schema = body.response_format?.json_schema?.name;
    const contents = body.messages.flatMap(message => typeof message.content === 'string' ? [{type:'text',text:message.content}] : message.content);
    const text = contents.filter(item=>item.type==='text').map(item=>item.text).join('\n');
    for (const item of contents.filter(item=>item.type==='image_url')) assert.match(item.image_url.url, /^data:image\/jpeg;base64,[A-Za-z0-9+/]+=*$/);
    let result;
    if (schema === 'technical_section_route') {
      routeCalls++;
      const pages = [...new Set([...text.matchAll(/PDF PAGE (\d+)/g)].map(match=>Number(match[1])))];
      result = {sections:pages.map(page=>({title:'Technical source',start_page:page,end_page:page,section_type:scenario==='unlocated-remark'||page===2?'compliance_schedule':'technical_requirements',reason:'Fixture source'})),uncertain_pages:[],routing_warnings:[]};
    } else if (schema === 'tender_source_column_map' || schema === 'visual_table_row_labels') {
      const page = Number([...text.matchAll(/(?:begins on PDF page|Rendered PDF page) (\d+)/g)].at(-1)?.[1]);
      const columns = ['single-content','mixed-native-heading'].includes(scenario) ? [{header:'Technical Parameters NIQ',role:'heading'},{header:'Remark',role:'remark'}] : [{header:'S. No.',role:'serial'},{header:'Specification',role:'heading'},{header:'Description',role:'specification'},
        ...(page===2?[{header:'Comply (Yes/No)',role:'compliance'},{header:'Remarks',role:'remark'}]:[])];
      result = schema === 'tender_source_column_map' ? {columns} : {columns,rows:[...text.matchAll(/^(\d+)\. CELL 0: (.*)$/gm)].map(match=>({row_index:Number(match[1]),row_type:Number(match[1])===2?'header':match[2].includes('Description')?'header':match[2].includes('A. Optical table')?'section':'requirement',category:'Other',continues_previous:false,heading_prefix:'',merge_with_next:false})),loose_headings:[],splits:[],visual_completions:[]};
      if(scenario==='mixed-native-heading'&&schema==='visual_table_row_labels'){for(const row of result.rows){const line=text.split('\n').find(line=>line.startsWith(row.row_index+'. CELL 0:'));if(line?.includes('16. Source shutter assembly'))row.row_type='section';}}
    } else if (schema === 'technical_table_page_rows') {
      const quote='The centrifuge shall accommodate 10 samples.';
      result={columns:[],requirements:scenario==='unlocated-remark'&&text.includes(quote)?[{page:1,quote,remark:'Invented deviation: maximum 500 RPM.',row_type:'requirement',category:'Performance',heading_prefix:'',display_lines:[quote],continues_previous:false}]:[]};
    } else if (schema === 'technical_table_missing_rows') {
      result={columns:[],requirements:[]};
    } else if (schema === 'technical_text_missing_requirements') {
      result = {columns:[],requirements:[
        ...(text.includes(recovery)?[{page:5,quote:recovery,category:'Performance',row_type:'requirement',heading_prefix:''}]:[]),
        ...(text.includes(outsideTable)?[{page:1,quote:outsideTable,category:'Other',row_type:'requirement',heading_prefix:''},{page:1,quote:'Required value 1 mm',category:'Other',row_type:'requirement',heading_prefix:''},{page:1,quote:'A. Optical table',category:'Other',row_type:'section',heading_prefix:''}]:[]),
      ]};
    } else if (schema === 'tender_requirements') {
      extractionCalls++;
      const pages = [...new Set([...text.matchAll(/PDF PAGE (\d+)/g)].map(match=>Number(match[1])))];
      const requirements=quotes.flatMap((quote,index)=>text.includes(quote)&&pages.includes(index+1)?[{page:index+1,quote,category:'Other',row_type:'requirement',heading_prefix:''}]:[]);
      result={columns:[],requirements:[...requirements,{page:pages[0],quote:'Invented limit of 999999 kN.',row_type:'requirement',category:'Other',heading_prefix:''},{page:999,quote:quotes[0],row_type:'requirement',category:'Other',heading_prefix:''}]};
      if(scenario==='injected-metadata')result.requirements=[{page:1,quote:quotes[0],row_type:'requirement',category:'Other',heading_prefix:'',sourceBox:{x:0,y:0,width:1,height:1},source_cells_exact:true,source_row_index:999,source_column_index:0,visualOcr:true},{page:1,quote:'The catalog shall specify ingress protection IP67.',row_type:'requirement',category:'Documentation',heading_prefix:''},{page:1,quote:'Payment terms are 30 days.',row_type:'requirement',category:'Other',heading_prefix:'',source_cells_exact:true},{page:1,quote:'(Indicate Compliance Status (Yes/No) for each and every point)',row_type:'requirement',category:'Other',heading_prefix:''},{page:1,quote:'All points indicated above (Annexure - II) must be filled by the bidder and relevant documents (i.e. catalogue, literature etc.) should be submitted.',row_type:'requirement',category:'Other',heading_prefix:''}];
      if(scenario==='case-sensitive')result={columns:[],requirements:[...text.matchAll(/Optical power shall be 1 (?:mW|MW)\./g)].map(match=>({page:1,quote:match[0],category:'Other',row_type:'requirement',heading_prefix:''}))};
      if(scenario==='invalid-capacity')result.requirements.push(...Array.from({length:300},(_,index)=>({page:1,quote:`Invented unsupported parameter ${index}.`,row_type:'requirement',category:'Other',heading_prefix:''})));
      if(scenario==='verified-capacity')result={columns:[],requirements:[...text.matchAll(/Capacity parameter (\d+) shall be (\d+) mm\./g)].map(match=>({page:Math.floor((Number(match[1])-1)/50)+1,quote:match[0],category:'Other',row_type:'requirement',heading_prefix:''}))};
    } else throw new Error(`Unexpected provider operation: ${schema}`);
    response.writeHead(200, {'content-type':'application/json'});
    response.end(JSON.stringify({choices:[{message:{content:JSON.stringify(result)}}]}));
  } catch(error) {response.writeHead(500);response.end(JSON.stringify({error:String(error)}));}
});
provider.listen(0,'127.0.0.1'); await once(provider,'listening');
const portProbe=http.createServer();portProbe.listen(0,'127.0.0.1');await once(portProbe,'listening');const appPort=portProbe.address().port;await new Promise(resolve=>portProbe.close(resolve));
const child=spawn(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',String(appPort)],{
  cwd:process.cwd(),env:{...process.env,OPENAI_API_KEY:'fixture-only-key',OPENAI_BASE_URL:`http://127.0.0.1:${provider.address().port}`,OPENAI_MODEL:'gpt-6-luna'},stdio:['ignore','pipe','pipe'],
});
let logs='';child.stdout.on('data',chunk=>{logs+=chunk;});child.stderr.on('data',chunk=>{logs+=chunk;});
try {
  const base=`http://127.0.0.1:${appPort}`;
  let ready=false;
  for(let attempt=0;attempt<100;attempt++) {
    if(child.exitCode!==null) throw new Error('Test app exited: '+logs.slice(-1500));
    try {if((await fetch(base,{signal:AbortSignal.timeout(1000)})).ok){ready=true;break;}}catch{}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  assert.ok(ready,'Test app ready');
  async function analyze(pdf) {
    const body=new FormData();body.set('file',new File([pdf.output('arraybuffer')],'synthetic-tender.pdf',{type:'application/pdf'}));
    return consumeAnalysisStream(await fetch(base+'/api/analyze',{method:'POST',body}),{onProgress:()=>{}});
  }
  const short=new jsPDF();short.text(quotes[0],20,30);
  const one=await analyze(short);
  assert.equal(one.ok,true,one.error);
  assert.equal(one.analysis.document.documentFingerprint,createHash('sha256').update(Buffer.from(short.output('arraybuffer'))).digest('hex'));
  assert.equal(one.analysis.requirements.length,1);
  assert.equal(one.analysis.requirements[0].quote,quotes[0]);
  scenario='injected-metadata';
  const injectedPdf=new jsPDF();injectedPdf.text(quotes[0],20,30);injectedPdf.text('The catalog shall specify ingress protection IP67.',20,50);injectedPdf.text('Payment terms are 30 days.',20,70);injectedPdf.text('(Indicate Compliance Status (Yes/No) for each and every point)',20,90);injectedPdf.text('All points indicated above (Annexure - II) must be filled by the bidder and relevant documents (i.e. catalogue, literature etc.) should be submitted.',20,110);
  const injected=await analyze(injectedPdf);assert.equal(injected.ok,true,injected.error);
  assert.equal(injected.analysis.requirements.length,2);
  assert.deepEqual(injected.analysis.requirements.map(row=>row.quote),[quotes[0],'The catalog shall specify ingress protection IP67.']);
  assert.ok(injected.analysis.requirements[0].bbox.x>5,'Model sourceBox cannot replace native quote geometry');
  assert.equal(injected.analysis.requirements[0].sourceReference.sourceCell,undefined);
  assert.equal(injected.analysis.requirements[0].ocrWarning,false);
  assert.equal(injected.analysis.requirements[1].reviewed,false,'Documentary obligations remain unreviewed');
  assert.equal(injected.analysis.requirements[1].sourceReference.locationPrecision,'exact');
  assert.equal(injected.analysis.requirements[1].sourceReference.sourceText,'The catalog shall specify ingress protection IP67.');
  assert.ok(injected.analysis.rejectedSuggestionDetails.some(row=>row.reason==='administrative_procurement_clause'));
  assert.ok(injected.analysis.rejectedSuggestionDetails.some(row=>row.quotePreview?.includes('Indicate Compliance Status')));
  assert.ok(injected.analysis.rejectedSuggestionDetails.some(row=>row.quotePreview?.includes('filled by the bidder')));
  scenario='unlocated-remark';
  const remarkPdf=new jsPDF();remarkPdf.text('The centrifuge shall accommodate 10 samples.',20,30);
  const remarkResult=await analyze(remarkPdf);assert.equal(remarkResult.ok,true,remarkResult.error);
  assert.equal(remarkResult.analysis.requirements.length,1,'A valid source-backed requirement survives an unlocatable optional remark');
  assert.equal(remarkResult.analysis.requirements[0].quote,'The centrifuge shall accommodate 10 samples.');
  assert.equal(remarkResult.analysis.requirements[0].remark,undefined,'Unverified remarks cannot be returned or exported');
  assert.equal(remarkResult.analysis.requirements[0].reviewed,false);
  assert.ok(remarkResult.analysis.requirements[0].bbox,'The primary quote keeps its own source location');
  assert.match(remarkResult.analysis.reviewNote,/unverified Remark field was omitted/);
  assert.ok(!JSON.stringify(buildResponseSheet(remarkResult.analysis)).includes('Invented deviation'));
  scenario='case-sensitive';
  const unitPdf=new jsPDF();unitPdf.text('Optical power shall be 1 mW.',20,30);unitPdf.text('Optical power shall be 1 MW.',20,50);
  const unitResult=await analyze(unitPdf);assert.equal(unitResult.ok,true,unitResult.error);
  assert.deepEqual(unitResult.analysis.requirements.map(row=>row.quote),['Optical power shall be 1 mW.','Optical power shall be 1 MW.']);
  scenario='invalid-capacity';
  const invalidCapacity=await analyze(short);
  assert.equal(invalidCapacity.ok,true,invalidCapacity.error);
  assert.equal(invalidCapacity.analysis.requirements.length,1,'Rejected model suggestions do not consume verified review capacity');
  assert.ok(invalidCapacity.analysis.rejectedCandidates>=300);
  scenario='verified-capacity';
  const capacityPdf=new jsPDF({unit:'pt'});
  for(let index=1;index<=251;index++){
    if(index>1&&(index-1)%50===0)capacityPdf.addPage();
    capacityPdf.setFontSize(8);capacityPdf.text(`Capacity parameter ${index} shall be ${index} mm.`,30,30+((index-1)%50)*14);
  }
  const capacity=await analyze(capacityPdf);
  assert.equal(capacity.ok,false,'Oversized verified sheets stop without partial output');
  assert.match(capacity.error,/251 verified response rows/);
  assert.equal(capacity.analysis,undefined);
  scenario='single-content';
  const single=new jsPDF({unit:'pt'});single.setFontSize(9);single.text('TECHNICAL SPECIFICATION',40,45);
  [['Technical Parameters NIQ','Remark'],['Optical power shall be 1 mW.',''],['Vacuum shall remain below 1 mbar.',''],['Pressure shall remain below 2 Pa.','']].forEach((cells,row)=>{let x=40;cells.forEach((value,column)=>{const width=column===0?370:130;single.rect(x,70+row*35,width,35);if(value)single.text(value,x+3,(row===0&&column===1?80:88)+row*35);x+=width;});});
  const singleResult=await analyze(single);assert.equal(singleResult.ok,true,singleResult.error);
  assert.ok(singleResult.analysis.requirements.every(row=>!row.sourceSectionHeadings?.includes('Remark')),'Vertically aligned response headers stay inside the table');
  assert.equal(singleResult.analysis.normalizedTables,true);assert.equal(singleResult.analysis.requirements.length,3);
  assert.ok(singleResult.analysis.requirements.every(row=>row.sourceReference.sourceCell));
  const singleSections=buildResponseSections(buildResponseSheet(singleResult.analysis));
  assert.equal(singleSections[0].columns[0].header,'Technical Parameters NIQ');
  assert.equal(singleSections[0].columnIndices[0],3,'No invented empty parameter column');
  assert.equal(singleSections[0].rows.length,3);
  scenario='mixed-native-heading';
  const mixedTitle='16. Source shutter assembly',mixedBody='The system shall withstand 300 N.';
  const mixedPdf=new jsPDF({unit:'pt'});mixedPdf.setFontSize(9);mixedPdf.text('TECHNICAL SPECIFICATION',40,45);
  [['Technical Parameters NIQ','Remark'],[mixedTitle,''],['Optical power shall be 1 mW.',''],['Vacuum shall remain below 1 mbar.','']].forEach((cells,row)=>{let x=40;cells.forEach((value,column)=>{const width=column===0?370:130;mixedPdf.rect(x,70+row*60,width,60);if(row===1&&column===0){mixedPdf.setFont('helvetica','bold');mixedPdf.text(value,x+3,88+row*60);mixedPdf.setFont('helvetica','normal');mixedPdf.text(mixedBody,x+3,102+row*60);}else if(value)mixedPdf.text(value,x+3,88+row*60);x+=width;});});
  const mixedHeading=await analyze(mixedPdf);assert.equal(mixedHeading.ok,true,mixedHeading.error);
  const mixedCell=mixedHeading.analysis.requirements.find(row=>row.quote.includes(mixedTitle));
  assert.equal(mixedCell.rowType,'requirement','A mixed source cell is assessable despite model section classification');
  assert.equal(mixedCell.headingPrefix,mixedTitle);assert.equal(mixedCell.nativeHeadingPrefix,mixedTitle);assert.ok(mixedCell.quote.includes(mixedBody));
  const mixedSheet=buildResponseSheet(mixedHeading.analysis);assert.equal(mixedSheet.rows[0].values[0],mixedTitle);assert.equal(mixedSheet.rows[0].values[3],mixedBody);
  assert.ok(mixedCell.sourceReference.sourceCell,'Full-cell source identity retained');
  scenario='prose';
  const pdf=new jsPDF();
  quotes.forEach((quote,index)=>{if(index)pdf.addPage();pdf.text('Technical requirements',20,20);pdf.text(quote,20,40);if(index===4)pdf.text(recovery,20,60);});
  const result=await analyze(pdf);
  assert.equal(result.ok,true,result.error);
  const analysis=result.analysis;
  assert.equal(analysis.requirements.length,6);
  assert.deepEqual(analysis.requirements.map(row=>row.quote),[...quotes,recovery]);
  for(const row of analysis.requirements){
    assert.equal(row.reviewed,false);
    assert.equal(row.sourceReference.locationPrecision,'exact');
    assert.equal(row.sourceReference.sourceText.replace(/\s+/g,' ').trim(),row.quote);
    assert.ok(row.bbox.width>0&&row.bbox.height>0);
    assert.equal(row.sourceReference.physicalPdfPageNumber,row.page);
    assert.equal(row.sourceReference.documentFingerprint,analysis.document.documentFingerprint);
  }
  assert.ok(analysis.rejectedSuggestionDetails.some(row=>row.reason==='source_quote_or_location_not_verified'));
  assert.ok(analysis.rejectedSuggestionDetails.some(row=>row.reason==='page_not_selected_by_router'));
  assert.equal(analysis.coverage.summary.selectedTechnicalPages,5);
  assert.ok(extractionCalls>=3,'Multiple bounded extraction batches used');
  let sheet=buildResponseSheet(analysis);
  const pageColumn=sheet.columns.findIndex(column=>column.role==='page');
  const requirementColumn=sheet.columns.findIndex(column=>column.role==='requirement');
  sheet=updateResponseSheetCell(sheet,sheet.rows[0].id,requirementColumn,'Reviewed edit');
  assert.equal(sheet.rows[0].values[requirementColumn],'Reviewed edit');
  const locked=sheet.rows[0].values[pageColumn];
  sheet=updateResponseSheetCell(sheet,sheet.rows[0].id,pageColumn,'Fake page');assert.equal(sheet.rows[0].values[pageColumn],locked);
  assert.equal(removeResponseSheetRow(sheet,sheet.rows[0].id).rows.length,5);
  scenario='tables';
  const tables=new jsPDF({unit:'pt',format:'a4'});
  for(let page=1;page<=2;page++){
    if(page>1)tables.addPage();
    if(page===1){tables.setFontSize(6);tables.rect(40,0,515,12);tables.text('Letterhead contact details',43,8);}
    const widths=page===1?[35,100,380]:[35,100,230,75,75];
    const sourceRows=[['A. Optical table',...widths.slice(1).map(()=>'')],['S. No.','Specification','Description',...(page===2?['Comply (Yes/No)','Remarks']:[])],
      ...Array.from({length:16},(_,index)=>[String(index+1),`Parameter ${index+1}`,`Required value ${index+1} mm`,...(page===2?['','']:[])])];
    tables.setFontSize(11);tables.text(page===1?'Annexure I':'Annexure II',40,25);tables.text(page===1?'Technical Specifications for Optical Tables':'Technical Compliance Report for Optical Tables',40,45);
    tables.setFontSize(8);
    sourceRows.forEach((cells,row)=>{let x=40;cells.forEach((value,column)=>{tables.rect(x,70+row*26,widths[column],26);if(value)tables.text(value,x+3,85+row*26);x+=widths[column];});});
    if(page===1)tables.text(outsideTable,40,600);
  }
  tables.addPage();tables.text('Technical safety requirements',40,40);tables.text(quotes[2],40,70);
  const mixed=await analyze(tables);
  assert.equal(mixed.ok,true,mixed.error);
  assert.equal(mixed.analysis.normalizedTables,true);
  assert.ok(mixed.analysis.requirements.some(row=>row.sourceSectionHeadings?.includes('Technical Specifications for Optical Tables')));
  assert.ok(mixed.analysis.requirements.some(row=>row.sourceSectionHeadings?.includes('Technical Compliance Report for Optical Tables')));
  const grouped=buildResponseSheet(mixed.analysis);
  assert.equal(grouped.rows.length,34,'Both tables, prose outside the grid, and the prose page retained');
  assert.equal(grouped.rows.filter(row=>row.values[7]==='Page 1').length,17);
  assert.equal(grouped.rows.filter(row=>row.values[7]==='Page 2').length,16);
  const projected=buildResponseSections(grouped);
  assert.deepEqual(projected.map(section=>section.rows.length),[16,1,16,1]);
  assert.equal(projected[0].annexure,'Annexure I');assert.equal(projected[2].annexure,'Annexure II');
  assert.ok(projected.every(section=>section.columns.every(column=>column.role!=='heading'&&column.role!=='page')));
  assert.equal(grouped.rows.filter(row=>row.values[0]==='A. Optical table').length,32);
  assert.ok(mixed.analysis.requirements.some(row=>row.quote===outsideTable&&row.sourceReference.locationPrecision==='exact'));
  assert.ok(!mixed.analysis.requirements.some(row=>row.quote.includes('Letterhead contact')));
  assert.ok(grouped.rows.every(row=>row.values[4]===''&&row.values[5]===''));
  assert.ok(grouped.rows.some(row=>row.values[3]===quotes[2]&&row.values[7]==='Page 3'));
  console.log(JSON.stringify({passed:true,cases:['model cannot assert source location or bypass technical filtering','mixed bold heading retains assessable body','single-content source table preserved','case-sensitive units retained','equal recovery quotes not duplicated','unsupported suggestions do not consume review capacity','verified response limit rejects without partial output','short unfamiliar clause','mixed schedule and prose','bounded five-page extraction','audit recovery','invented numeric rejection','invalid page rejection','exact source evidence','editable sheet with locked citations','different table schemas plus narrative page','16-row equipment grouping'],routeCalls,extractionCalls}));
} finally {
  child.kill('SIGTERM');
  if(child.exitCode===null)await Promise.race([once(child,'exit'),new Promise(resolve=>setTimeout(resolve,3000))]);
  if(child.exitCode===null)child.kill('SIGKILL');
  provider.closeAllConnections();await new Promise(resolve=>provider.close(resolve));
}
