// Deterministic contract test: real PDF parsing/API/SSE/source validation/sheet edits,
// scripted provider responses. This does not measure the live model's recall.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import http from 'node:http';
import { once } from 'node:events';
import { spawn } from 'node:child_process';
import { jsPDF } from 'jspdf';
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
      result = {sections:pages.map(page=>({title:'Technical source',start_page:page,end_page:page,section_type:page===2?'compliance_schedule':'technical_requirements',reason:'Fixture source'})),uncertain_pages:[],routing_warnings:[]};
    } else if (schema === 'tender_source_column_map' || schema === 'visual_table_row_labels') {
      const page = Number([...text.matchAll(/(?:begins on PDF page|Rendered PDF page) (\d+)/g)].at(-1)?.[1]);
      const columns = [{header:'S. No.',role:'serial'},{header:'Specification',role:'heading'},{header:'Description',role:'specification'},
        ...(page===2?[{header:'Comply (Yes/No)',role:'compliance'},{header:'Remarks',role:'remark'}]:[])];
      result = schema === 'tender_source_column_map' ? {columns} : {columns,rows:[...text.matchAll(/^(\d+)\. CELL 0: (.*)$/gm)].map(match=>({row_index:Number(match[1]),row_type:Number(match[1])===2?'header':match[2].includes('Description')?'header':match[2].includes('A. Optical table')?'section':'requirement',category:'Other',continues_previous:false,heading_prefix:'',merge_with_next:false})),loose_headings:[],splits:[],visual_completions:[]};
    } else if (schema === 'technical_text_missing_requirements') {
      result = {columns:[],requirements:text.includes(recovery)?[{page:5,quote:recovery,category:'Performance',row_type:'requirement',heading_prefix:''}]:[]};
    } else if (schema === 'tender_requirements') {
      extractionCalls++;
      const pages = [...new Set([...text.matchAll(/PDF PAGE (\d+)/g)].map(match=>Number(match[1])))];
      const requirements=quotes.flatMap((quote,index)=>text.includes(quote)&&pages.includes(index+1)?[{page:index+1,quote,category:'Other',row_type:'requirement',heading_prefix:''}]:[]);
      result={columns:[],requirements:[...requirements,{page:pages[0],quote:'Invented limit of 999999 kN.',row_type:'requirement',category:'Other',heading_prefix:''},{page:999,quote:quotes[0],row_type:'requirement',category:'Other',heading_prefix:''}]};
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
    const widths=page===1?[35,100,380]:[35,100,230,75,75];
    const sourceRows=[['A. Optical table',...widths.slice(1).map(()=>'')],['S. No.','Specification','Description',...(page===2?['Comply (Yes/No)','Remarks']:[])],
      ...Array.from({length:16},(_,index)=>[String(index+1),`Parameter ${index+1}`,`Required value ${index+1} mm`,...(page===2?['','']:[])])];
    tables.setFontSize(8);
    sourceRows.forEach((cells,row)=>{let x=40;cells.forEach((value,column)=>{tables.rect(x,70+row*26,widths[column],26);if(value)tables.text(value,x+3,85+row*26);x+=widths[column];});});
  }
  tables.addPage();tables.text('Technical safety requirements',40,40);tables.text(quotes[2],40,70);
  const mixed=await analyze(tables);
  assert.equal(mixed.ok,true,mixed.error);
  assert.equal(mixed.analysis.normalizedTables,true);
  const grouped=buildResponseSheet(mixed.analysis);
  assert.equal(grouped.rows.length,33,'Both 16-row tables and the prose page retained');
  assert.equal(grouped.rows.filter(row=>row.values[7]==='Page 1').length,16);
  assert.equal(grouped.rows.filter(row=>row.values[7]==='Page 2').length,16);
  assert.ok(grouped.rows.slice(0,32).every(row=>row.values[0]==='A. Optical table'));
  assert.ok(grouped.rows.every(row=>row.values[4]===''&&row.values[5]===''));
  assert.ok(grouped.rows.some(row=>row.values[3]===quotes[2]&&row.values[7]==='Page 3'));
  console.log(JSON.stringify({passed:true,cases:['short unfamiliar clause','mixed schedule and prose','bounded five-page extraction','audit recovery','invented numeric rejection','invalid page rejection','exact source evidence','editable sheet with locked citations','different table schemas plus narrative page','16-row equipment grouping'],routeCalls,extractionCalls}));
} finally {
  child.kill('SIGTERM');
  if(child.exitCode===null)await Promise.race([once(child,'exit'),new Promise(resolve=>setTimeout(resolve,3000))]);
  if(child.exitCode===null)child.kill('SIGKILL');
  provider.closeAllConnections();await new Promise(resolve=>provider.close(resolve));
}
