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
let initialExtractionReturnedRecovery = false;
let omissionAuditReturnedRecovery = false;
let corruptedNumericClaimProposed = false;
const visualBatchObservations = [];
let activeVectorLabelRequests = 0;
let maximumVectorLabelConcurrency = 0;
let vectorLabelRequestCount = 0;
let activeGeneralExtractionRequests = 0;
let maximumGeneralExtractionConcurrency = 0;
const generalExtractionBatchEvents = [];
const vectorAuditPageOrder = [];
const progressObservations = [];
const provider = http.createServer(async (request, response) => {
  let trackedVectorLabelRequest = false;
  let trackedGeneralExtractionRequest = false;
  let trackedGeneralExtractionFirstPage = 0;
  try {
    let raw = '';
    for await (const chunk of request) raw += chunk;
    const body = JSON.parse(raw);
    const schema = body.response_format?.json_schema?.name;
    if (scenario === 'slow-general-extraction' && schema === 'tender_requirements') await new Promise(resolve => setTimeout(resolve, 150));
    if (scenario === 'general-batch-concurrency' && schema === 'tender_requirements') {
      trackedGeneralExtractionRequest = true;
      activeGeneralExtractionRequests += 1;
      maximumGeneralExtractionConcurrency = Math.max(maximumGeneralExtractionConcurrency, activeGeneralExtractionRequests);
      const pages = [...new Set([...raw.matchAll(/PDF PAGE (\d+)/g)].map(match => Number(match[1])))];
      const firstPage = pages[0] ?? 0;
      trackedGeneralExtractionFirstPage = firstPage;
      generalExtractionBatchEvents.push({ firstPage, event: 'started', at: Date.now() });
      await new Promise(resolve => setTimeout(resolve, firstPage === 1 ? 40 : firstPage === 4 ? 160 : firstPage === 7 ? 220 : 60));
    }
    if (scenario === 'vector-page-concurrency' && schema === 'visual_table_row_labels') {
      trackedVectorLabelRequest = true;
      activeVectorLabelRequests += 1;
      vectorLabelRequestCount += 1;
      maximumVectorLabelConcurrency = Math.max(maximumVectorLabelConcurrency, activeVectorLabelRequests);
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (scenario === 'vector-page-concurrency' && schema === 'source_row_semantic_coverage') {
      const auditInput = body.messages.at(-1)?.content ?? '';
      const pageMatch = auditInput.match(/Maximum load on unit (\d+)/);
      if (pageMatch) vectorAuditPageOrder.push(Number(pageMatch[1]));
    }
    const contents = body.messages.flatMap(message => typeof message.content === 'string' ? [{type:'text',text:message.content}] : message.content);
    const text = contents.filter(item=>item.type==='text').map(item=>item.text).join('\n');
    if (schema === 'technical_table_page_batch_rows' || schema === 'technical_table_missing_rows') visualBatchObservations.push({scenario,schema,imageCount:contents.filter(item=>item.type==='image_url').length});
    for (const item of contents.filter(item=>item.type==='image_url')) assert.match(item.image_url.url, /^data:image\/jpeg;base64,[A-Za-z0-9+/]+=*$/);
    let result;
    if (schema === 'technical_section_route') {
      routeCalls++;
      const pages = [...new Set([...text.matchAll(/PDF PAGE (\d+)/g)].map(match=>Number(match[1])))];
      result = {sections:['page-disposition-only','possibly-relevant-page','unrouted-page'].includes(scenario)?[]:pages.map(page=>({title:'Technical source',start_page:page,end_page:page,section_type:scenario==='unlocated-remark'||scenario==='page-batched-fallback'||page===2?'compliance_schedule':'technical_requirements',reason:'Fixture source'})),uncertain_pages:scenario==='possibly-relevant-page'?pages:[],page_dispositions:scenario==='unrouted-page'?[]:pages.map(page=>({page,classification:scenario==='possibly-relevant-page'?'possibly_relevant':'relevant',reason:scenario==='possibly-relevant-page'?'The page excerpt is ambiguous and may contain technical obligations.':'Fixture source contains a technical test case.'})),routing_warnings:[],possible_source_conflicts:scenario==='cross-section-conflict'?[{page_a:1,quote_a:'X-Band EPR spectrometer system',page_b:2,quote_b:'Advanced Spectrofluorometer',reason:'The two supplied sections identify different equipment subjects.'}]:scenario==='unsupported-section-conflict'?[{page_a:1,quote_a:'X-Band EPR spectrometer system',page_b:2,quote_b:'EPR spectrometer',reason:'The two supplied sections identify different equipment subjects.'}]:[]};
    } else if (schema === 'tender_source_column_map' || schema === 'visual_table_row_labels') {
      const page = Number([...text.matchAll(/(?:begins on PDF page|Rendered PDF page) (\d+)/g)].at(-1)?.[1]);
      const independentVectorColumns = scenario === 'vector-page-concurrency' ? [
        [{header:'Technical Parameters NIQ',role:'heading'},{header:'Remark',role:'remark'}],
        [],
        [{header:'S. No.',role:'serial'},{header:'Parameter',role:'heading'},{header:'Specification',role:'specification'}],
      ][page - 1] : null;
      const columns = independentVectorColumns ?? (['single-content','mixed-native-heading','visual-completion'].includes(scenario) ? [{header:'Technical Parameters NIQ',role:'heading'},{header:'Remark',role:'remark'}] : [{header:'S. No.',role:'serial'},{header:'Specification',role:'heading'},{header:'Description',role:'specification'},
        ...(page===2&&scenario!=='vector-page-concurrency'?[{header:'Comply (Yes/No)',role:'compliance'},{header:'Remarks',role:'remark'}]:[])]);
      result = schema === 'tender_source_column_map' ? {columns} : {columns,rows:[...text.matchAll(/^(\d+)\. CELL 0: (.*)$/gm)].map(match=>{
        const row_type=match[2].includes('Description')||match[2].includes('S. No.')?'header':match[2].includes('A. Optical table')?'section':match[2].includes('Unclear source row')?'ambiguous':'requirement';
        const classification_reason={header:'header_or_page_furniture',section:'structural_heading',ambiguous:'ambiguous_source_structure',requirement:'technical_obligation'}[row_type];
        return {row_index:Number(match[1]),row_type,classification_reason,category:'Other',continues_previous:false,heading_prefix:'',merge_with_next:false};
      }),loose_headings:[],splits:[],visual_completions:[]};
      if(scenario==='visual-completion'&&schema==='visual_table_row_labels'){
        const row=result.rows.find(candidate=>text.includes(`${candidate.row_index}. CELL 0: Pump shall deliver 200 bar`));
        if(row)result.visual_completions=[{row_index:row.row_index,quote:'Pump shall deliver 200 bar and be compatible with ISO 9001',confidence:'high'}];
      }
      if(scenario==='mixed-native-heading'&&schema==='visual_table_row_labels'){for(const row of result.rows){const line=text.split('\n').find(line=>line.startsWith(row.row_index+'. CELL 0:'));if(line?.includes('16. Source shutter assembly')){row.row_type='section';row.classification_reason='structural_heading';}}}
    } else if (schema === 'technical_table_page_batch_rows') {
      const quote='The centrifuge shall accommodate 10 samples.';
      result={page_results:[{page:1,columns:[],requirements:['unlocated-remark','page-batched-fallback'].includes(scenario)&&text.includes(quote)?[{quote,visual_region_index:0,remark:scenario==='unlocated-remark'?'Invented deviation: maximum 500 RPM.':'',row_type:'requirement',category:'Performance',heading_prefix:'',display_lines:[quote],continues_previous:false}]:[]}]};
    } else if (schema === 'technical_table_missing_rows') {
      result={columns:[],requirements:[]};
    } else if (schema === 'source_row_semantic_coverage') {
      const rows = JSON.parse(body.messages.at(-1)?.content ?? '[]');
      result = { rows: rows.map(row => row.source_cells.some(cell => cell.includes('Calibration report shall be supplied.'))
        ? { row_index: row.row_index, status: 'possible_gap', note: 'The source row contains a second independently assessable obligation.', missing_source_quotes: ['Calibration report shall be supplied.'] }
        : { row_index: row.row_index, status: 'no_gap_reported', note: '', missing_source_quotes: [] }) };
    } else if (schema === 'technical_text_missing_requirements') {
      const requirements=[
        ...(text.includes(recovery)?[{page:5,quote:recovery,category:'Performance',row_type:'requirement',heading_prefix:''}]:[]),
        ...(text.includes(outsideTable)?[{page:1,quote:outsideTable,category:'Other',row_type:'requirement',heading_prefix:''},{page:1,quote:'Required value 1 mm',category:'Other',row_type:'requirement',heading_prefix:''},{page:1,quote:'A. Optical table',category:'Other',row_type:'section',heading_prefix:''}]:[]),
      ];
      if(scenario==='prose'&&requirements.some(item=>item.quote===recovery))omissionAuditReturnedRecovery=true;
      result = {columns:[],requirements};
    } else if (schema === 'tender_requirements') {
      extractionCalls++;
      const pages = [...new Set([...text.matchAll(/PDF PAGE (\d+)/g)].map(match=>Number(match[1])))];
      const requirements=quotes.flatMap((quote,index)=>text.includes(quote)&&pages.includes(index+1)?[{page:index+1,quote,category:'Other',row_type:'requirement',heading_prefix:''}]:[]);
      result={columns:[],requirements:[...requirements,...(scenario==='prose'&&pages.includes(2)?[{page:2,quote:'Vacuum shall remain below 999999 mbar.',row_type:'requirement',category:'Other',heading_prefix:''}]:[]),{page:pages[0],quote:'Invented limit of 999999 kN.',row_type:'requirement',category:'Other',heading_prefix:''},{page:999,quote:quotes[0],row_type:'requirement',category:'Other',heading_prefix:''}]};
      if(scenario==='prose'&&result.requirements.some(item=>item.quote==='Vacuum shall remain below 999999 mbar.'))corruptedNumericClaimProposed=true;
      if(scenario==='prose'&&result.requirements.some(item=>item.quote===recovery))initialExtractionReturnedRecovery=true;
      if(scenario==='all-rejected')result={columns:[],requirements:Array.from({length:60},(_,index)=>({page:pages[0],quote:`Invented limit ${index} of 999999 kN.`,row_type:'requirement',category:'Other',heading_prefix:''}))};
      if(scenario==='no-candidates')result={columns:[],requirements:[]};
      if(scenario==='injected-metadata')result.requirements=[{page:1,quote:quotes[0],row_type:'requirement',category:'Other',heading_prefix:'',sourceBox:{x:0,y:0,width:1,height:1},source_cells_exact:true,source_row_index:999,source_column_index:0,visualOcr:true},{page:1,quote:'The catalog shall specify ingress protection IP67.',row_type:'requirement',category:'Documentation',heading_prefix:''},{page:1,quote:'Payment terms are 30 days.',row_type:'instruction',category:'Other',heading_prefix:'',source_cells_exact:true}];
      if(scenario==='case-sensitive')result={columns:[],requirements:[...text.matchAll(/Optical power shall be 1 (?:mW|MW)\./g)].map(match=>({page:1,quote:match[0],category:'Other',row_type:'requirement',heading_prefix:''}))};
      if(scenario==='invalid-capacity')result.requirements.push(...Array.from({length:300},(_,index)=>({page:1,quote:`Invented unsupported parameter ${index}.`,row_type:'requirement',category:'Other',heading_prefix:''})));
      if(scenario==='verified-capacity')result={columns:[],requirements:[...text.matchAll(/Capacity parameter (\d+) shall be (\d+) mm\./g)].map(match=>({page:Math.floor((Number(match[1])-1)/50)+1,quote:match[0],category:'Other',row_type:'requirement',heading_prefix:''}))};
    } else throw new Error(`Unexpected provider operation: ${schema}`);
    response.writeHead(200, {'content-type':'application/json'});
    response.end(JSON.stringify({choices:[{message:{content:JSON.stringify(result)}}]}));
  } catch(error) {response.writeHead(500);response.end(JSON.stringify({error:String(error)}));}
  finally {
    if (trackedGeneralExtractionRequest) {
      generalExtractionBatchEvents.push({ firstPage: trackedGeneralExtractionFirstPage, event: 'completed', at: Date.now() });
    }
    if (trackedVectorLabelRequest) activeVectorLabelRequests -= 1;
    if (trackedGeneralExtractionRequest) activeGeneralExtractionRequests -= 1;
  }
});
provider.listen(0,'127.0.0.1'); await once(provider,'listening');
const portProbe=http.createServer();portProbe.listen(0,'127.0.0.1');await once(portProbe,'listening');const appPort=portProbe.address().port;await new Promise(resolve=>portProbe.close(resolve));
const child=spawn(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',String(appPort)],{
  cwd:process.cwd(),env:{...process.env,OPENAI_API_KEY:'fixture-only-key',OPENAI_BASE_URL:`http://127.0.0.1:${provider.address().port}`,OPENAI_MODEL:'gpt-6-luna',APP_ACCESS_PASSWORD:'fixture-only-password'},stdio:['ignore','pipe','pipe'],
});
let logs='';child.stdout.on('data',chunk=>{logs+=chunk;});child.stderr.on('data',chunk=>{logs+=chunk;});
try {
  const base=`http://127.0.0.1:${appPort}`;
  let ready=false;
  let lastReadinessResponse='no response received';
  for(let attempt=0;attempt<100;attempt++) {
    if(child.exitCode!==null) throw new Error('Test app exited: '+logs.slice(-1500));
    try {
      const response=await fetch(base,{headers:{authorization:`Basic ${Buffer.from('tender:fixture-only-password').toString('base64')}`},signal:AbortSignal.timeout(1000)});
      lastReadinessResponse=`HTTP ${response.status}`;
      if(response.ok){ready=true;break;}
    }catch(error){lastReadinessResponse=String(error);}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  assert.ok(ready,`Test app ready (${lastReadinessResponse}): ${logs.slice(-1500)}`);
  const unauthenticatedPage = await fetch(base);
  assert.equal(unauthenticatedPage.status, 401, 'The application UI rejects anonymous requests');
  const unauthenticated = await fetch(`${base}/api/analyze`, { method: 'POST', body: new FormData() });
  assert.equal(unauthenticated.status, 401, 'The upload endpoint rejects anonymous requests before parsing or analysis');
  assert.match(unauthenticated.headers.get('www-authenticate') ?? '', /^Basic /);
  async function analyze(pdf) {
    const body=new FormData();body.set('file',new File([pdf.output('arraybuffer')],'synthetic-tender.pdf',{type:'application/pdf'}));
    const response = await fetch(base+'/api/analyze',{method:'POST',body,headers:{authorization:`Basic ${Buffer.from('tender:fixture-only-password').toString('base64')}`}});
    assert.match(response.headers.get('cache-control') ?? '', /private, no-store/);
    return consumeAnalysisStream(response,{onProgress:(progress)=>progressObservations.push({scenario, ...progress})});
  }
  const short=new jsPDF();short.text(quotes[0],20,30);
  const one=await analyze(short);
  assert.equal(one.ok,true,one.error);
  assert.equal(one.analysis.document.documentFingerprint,createHash('sha256').update(Buffer.from(short.output('arraybuffer'))).digest('hex'));
  assert.equal(one.analysis.document.inventoryIntegrity,'structurally-verified');
  assert.equal(one.analysis.requirements.length,1);
  assert.equal(one.analysis.requirements[0].quote,quotes[0]);
  scenario='slow-general-extraction';
  const slowGeneral=await analyze(short);
  assert.equal(slowGeneral.ok,true,slowGeneral.error);
  const slowExtractionProgress=progressObservations.filter(event=>event.scenario===scenario&&event.stage==='extracting').map(event=>event.message);
  const requestProgressIndex=slowExtractionProgress.findIndex(message=>message==='Requesting technical extraction batches 1–1 of 1');
  const completedProgressIndex=slowExtractionProgress.findIndex(message=>message==='Received and parsed 1 of 1 technical extraction batches');
  assert.ok(requestProgressIndex>=0&&completedProgressIndex>requestProgressIndex,`Extraction progress reports the active request before reporting its parsed completion: ${JSON.stringify(slowExtractionProgress)}`);
  scenario='general-batch-concurrency';
  const multiPage=new jsPDF();
  for(let page=1;page<=12;page++) {
    if(page>1)multiPage.addPage();
    multiPage.setFontSize(8);
    const pageQuote=quotes[page-1]??`Technical equipment page ${page} contains a specified test procedure.`;
    multiPage.text([pageQuote,...Array.from({length:60},(_,line)=>`Technical context ${page}-${line} describes the equipment and its operating conditions.`)],20,30,{lineHeightFactor:1});
  }
  const batched=await analyze(multiPage);
  assert.equal(batched.ok,true,batched.error);
  assert.equal(maximumGeneralExtractionConcurrency,3,'Independent general extraction batches run at the existing per-analysis concurrency limit');
  assert.deepEqual(batched.analysis.requirements.map(row=>row.quote),quotes,'Concurrent extraction preserves deterministic source order and all grounded fixture requirements');
  const batchedProgress=progressObservations.filter(event=>event.scenario===scenario&&event.stage==='extracting').map(event=>event.message);
  assert.ok(batchedProgress.includes('Received and parsed 4 of 4 technical extraction batches'));
  const batchThreeCompletedAt=generalExtractionBatchEvents.find(event=>event.firstPage===7&&event.event==='completed')?.at;
  const batchFourStartedAt=generalExtractionBatchEvents.find(event=>event.firstPage===10&&event.event==='started')?.at;
  assert.ok(Number.isFinite(batchThreeCompletedAt)&&Number.isFinite(batchFourStartedAt)&&batchFourStartedAt<batchThreeCompletedAt,'The fourth extraction batch starts when the first of the three active requests finishes, before the slow third request completes');
  scenario='page-disposition-only';
  const dispositionOnly=await analyze(short);
  assert.equal(dispositionOnly.ok,true,dispositionOnly.error);
  assert.equal(dispositionOnly.analysis.requirements.length,1,'A relevant per-page disposition selects source extraction even without a section range');
  assert.equal(dispositionOnly.analysis.coverage.pages[0].routingDisposition,'selected');
  scenario='possibly-relevant-page';
  const uncertainPage=await analyze(short);
  assert.equal(uncertainPage.ok,true,uncertainPage.error);
  assert.equal(uncertainPage.analysis.requirements.length,1,'A possibly relevant page receives the normal source-grounded extraction pass');
  assert.equal(uncertainPage.analysis.coverage.pages[0].routingDisposition,'uncertain','Deeper extraction does not erase the unresolved routing disposition');
  assert.equal(uncertainPage.analysis.coverage.pages[0].selectedForExtraction,true);
  scenario='unrouted-page';
  const unroute=await analyze(short);
  assert.equal(unroute.ok,true,unroute.error);
  assert.equal(unroute.analysis.requirements.length,1,'A page with no routing disposition receives source-grounded extraction');
  assert.equal(unroute.analysis.coverage.pages[0].routingDisposition,'unrouted','Extraction does not resolve a missing routing decision');
  assert.equal(unroute.analysis.coverage.pages[0].selectedForExtraction,true);
  scenario='page-batched-fallback';
  const batchedPdf=new jsPDF();batchedPdf.text('The centrifuge shall accommodate 10 samples.',20,30);
  const batchedFallback=await analyze(batchedPdf);
  assert.equal(batchedFallback.ok,true,batchedFallback.error);
  assert.equal(batchedFallback.analysis.requirements.length,1,'The page-batched visual fallback preserves the literal source requirement');
  assert.equal(batchedFallback.analysis.coverage.pages[0].auditStatus,'no_gaps_reported');
  assert.deepEqual(visualBatchObservations.filter(item=>item.scenario==='page-batched-fallback'),[
    {scenario:'page-batched-fallback',schema:'technical_table_page_batch_rows',imageCount:3},
    {scenario:'page-batched-fallback',schema:'technical_table_missing_rows',imageCount:3},
  ],'one extraction and one independent audit request each receive the three indexed page regions');
  scenario='cross-section-conflict';
  const conflictPdf=new jsPDF();conflictPdf.text('Technical specifications for X-Band EPR spectrometer system',20,30);conflictPdf.text(quotes[0],20,50);conflictPdf.addPage();conflictPdf.text('Advanced Spectrofluorometer compliance sheet',20,30);
  const conflict=await analyze(conflictPdf);assert.equal(conflict.ok,true,conflict.error);
  assert.match(conflict.analysis.reviewNote,/Possible cross-section inconsistency on PDF pages 1 and 2/);
  assert.match(conflict.analysis.reviewNote,/neither source is treated as authoritative/);
  assert.ok(conflict.analysis.coverage.pages.some(page=>page.page===1&&page.routerMarkedUncertain));
  assert.ok(conflict.analysis.coverage.pages.some(page=>page.page===2&&page.routerMarkedUncertain));
  assert.ok(conflict.analysis.coverage.pages.some(page=>page.page===1&&page.selectedForExtraction));
  assert.ok(conflict.analysis.coverage.pages.some(page=>page.page===2&&page.selectedForExtraction));
  scenario='unsupported-section-conflict';
  const unsupportedConflict=await analyze(conflictPdf);assert.equal(unsupportedConflict.ok,true,unsupportedConflict.error);
  assert.doesNotMatch(unsupportedConflict.analysis.reviewNote,/Possible cross-section inconsistency on PDF pages/);
  assert.match(unsupportedConflict.analysis.reviewNote,/could not be verified against both cited page transcripts/);
  scenario='injected-metadata';
  const injectedPdf=new jsPDF();injectedPdf.text(quotes[0],20,30);injectedPdf.text('The catalog shall specify ingress protection IP67.',20,50);injectedPdf.text('Payment terms are 30 days.',20,70);
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
  scenario='all-rejected';
  const rejectedOnlyPdf=new jsPDF();rejectedOnlyPdf.text('Technical requirements',20,20);rejectedOnlyPdf.text(quotes[0],20,40);
  const rejectedOnly=await analyze(rejectedOnlyPdf);
  assert.equal(rejectedOnly.ok,false,'Unsupported suggestions do not become requirements when none can be grounded');
  assert.equal(rejectedOnly.analysis,undefined);
  assert.equal(rejectedOnly.pageCount,1);
  assert.equal(rejectedOnly.rejectedCandidates,60);
  assert.equal(rejectedOnly.rejectedSuggestionDetails.length,50,'Failure diagnostics bound the displayed suggestion payload');
  assert.equal(rejectedOnly.rejectedSuggestionsNotShown,10);
  assert.equal(rejectedOnly.rejectedSuggestionDetails[0].reason,'source_quote_or_location_not_verified');
  assert.equal(rejectedOnly.rejectedSuggestionDetails[0].page,1);
  assert.equal(rejectedOnly.coverageSummary.rejectedSuggestions,60);
  assert.equal(rejectedOnly.coverageSummary.sourceMatchedRows,0);
  scenario='no-candidates';
  const noCandidates=await analyze(short);
  assert.equal(noCandidates.ok,false,'An empty model extraction must stop without success-shaped output');
  assert.equal(noCandidates.candidateSuggestions,0);
  assert.deepEqual(noCandidates.rejectedSuggestionDetails,[]);
  assert.match(noCandidates.error,/empty extraction is not evidence/i);
  assert.ok(noCandidates.reviewPageNumbers.includes(1),'The reviewer can locate selected pages even when no candidate was returned');
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
  scenario='vector-page-concurrency';
  const vectorPagesPdf=new jsPDF({unit:'pt'});vectorPagesPdf.setFontSize(9);
  for(let page=1;page<=3;page++){
    if(page>1)vectorPagesPdf.addPage();
    vectorPagesPdf.text('TECHNICAL SPECIFICATION',40,45);
    const tableRows = page===1
      ? [['Technical Parameters NIQ','Remark'],[`Maximum load on unit ${page} shall be 10 kN.`,''],['Supply voltage shall be 230 V AC.',''],['Operating temperature shall be -10 to 50 °C.','']]
      : page===2
        ? [[`Maximum load on unit ${page} shall be 10 kN.`,''],['Supply voltage shall be 230 V AC.',''],['Operating temperature shall be -10 to 50 °C.',''],['Crosshead speed shall be 500 mm/min.',''],['Load accuracy shall be within 1%.','']]
        : [['S. No.','Parameter','Specification'],['1','Load frame',`Maximum load on unit ${page} shall be 10 kN.`],['2','Power','Supply voltage shall be 230 V AC.'],['3','Temperature','Operating temperature shall be -10 to 50 °C.']];
    const widths=page===1?[370,130]:page===2?[140,280,80]:[55,140,305];
    tableRows.forEach((cells,row)=>{
      let x=40;
      cells.forEach((value,column)=>{vectorPagesPdf.rect(x,70+row*38,widths[column],38);if(value)vectorPagesPdf.text(value,x+3,88+row*38);x+=widths[column];});
    });
  }
  const vectorPagesResult=await analyze(vectorPagesPdf);
  assert.equal(vectorPagesResult.ok,true,`${vectorPagesResult.error} (route calls ${routeCalls}; vector labels ${vectorLabelRequestCount}; peak concurrency ${maximumVectorLabelConcurrency})`);
  assert.equal(vectorLabelRequestCount,3,`Each detected vector-table page receives a page-local classification request (${JSON.stringify(vectorPagesResult.analysis.coverage.pages.map(page=>({page:page.page,rows:page.sourceTableRowsDetected,status:page.extractionStatus,routing:page.routingDisposition})))})`);
  assert.equal(maximumVectorLabelConcurrency,3,`Independent vector pages run concurrently up to the model-client limit (classified ${vectorLabelRequestCount}; audit order ${vectorAuditPageOrder.join(',')})`);
  assert.deepEqual(vectorAuditPageOrder,[1,2,3],'The analysis-wide row-audit budget is consumed in source-page order');
  assert.deepEqual(vectorPagesResult.analysis.requirements.map(row=>row.page),[1,1,1,2,2,2,2,2,3,3,3],'Returned requirements preserve source page order');
  assert.equal(vectorPagesResult.analysis.requirements.find(row=>row.page===2)?.quote,'Maximum load on unit 2 shall be 10 kN.','A headerless continuation retains its inherited specification column');
  assert.equal(vectorPagesResult.analysis.requirements.find(row=>row.page===2)?.sourceColumnMap?.[0]?.header,'Technical Parameters NIQ','A headerless continuation inherits the prior verified page map');
  assert.equal(vectorPagesResult.analysis.requirements.find(row=>row.page===3)?.sourceColumnMap?.[2]?.header,'Specification');
  assert.ok(vectorPagesResult.analysis.requirements.every(row=>row.sourceReference.sourceCell),'Parallel inspection preserves source-row citations');
  scenario='mixed-native-heading';
  const mixedTitle='16. Source shutter assembly',mixedBody='The system shall withstand 300 N.';
  const mixedPdf=new jsPDF({unit:'pt'});mixedPdf.setFontSize(9);mixedPdf.text('TECHNICAL SPECIFICATION',40,45);
  [['Technical Parameters NIQ','Remark'],[mixedTitle,''],['Optical power shall be 1 mW.',''],['Vacuum shall remain below 1 mbar.','']].forEach((cells,row)=>{let x=40;cells.forEach((value,column)=>{const width=column===0?370:130;mixedPdf.rect(x,70+row*60,width,60);if(row===1&&column===0){mixedPdf.setFont('helvetica','bold');mixedPdf.text(value,x+3,88+row*60);mixedPdf.setFont('helvetica','normal');mixedPdf.text(mixedBody,x+3,102+row*60);}else if(value)mixedPdf.text(value,x+3,88+row*60);x+=width;});});
  const mixedHeading=await analyze(mixedPdf);assert.equal(mixedHeading.ok,true,mixedHeading.error);
  const mixedCell=mixedHeading.analysis.requirements.find(row=>row.quote.includes(mixedTitle));
  assert.equal(mixedCell.rowType,'requirement','A mixed source cell is assessable despite model section classification');
  const mixedSourceRow=mixedHeading.analysis.coverage.pages.flatMap(page=>page.sourceTableCoverageRows??[]).find(row=>row.cells.some(cell=>cell.includes(mixedTitle)));
  assert.equal(mixedSourceRow.sourceClassification,'requirement');
  assert.equal(mixedSourceRow.classificationReason,'technical_obligation');
  assert.equal(mixedCell.headingPrefix,mixedTitle);assert.equal(mixedCell.nativeHeadingPrefix,mixedTitle);assert.ok(mixedCell.quote.includes(mixedBody));
  const mixedSheet=buildResponseSheet(mixedHeading.analysis);assert.equal(mixedSheet.rows[0].values[0],mixedTitle);assert.equal(mixedSheet.rows[0].values[3],mixedBody);
  assert.ok(mixedCell.sourceReference.sourceCell,'Full-cell source identity retained');
  scenario='visual-completion';
  const completionPdf=new jsPDF({unit:'pt'});completionPdf.setFontSize(9);completionPdf.text('TECHNICAL SPECIFICATION',40,45);
  [['Technical Parameters NIQ','Remark'],['Pump shall deliver 200 bar',''],['Supply voltage shall be 230 V AC',''],['Maximum flow shall be 20 L/min','']].forEach((cells,row)=>{let x=40;cells.forEach((value,column)=>{const width=column===0?370:130;completionPdf.rect(x,70+row*45,width,45);if(value)completionPdf.text(value,x+3,88+row*45);x+=width;});});
  const completion=await analyze(completionPdf);assert.equal(completion.ok,true,completion.error);
  const completionRow=completion.analysis.requirements.find(row=>row.quote==='Pump shall deliver 200 bar');
  assert.ok(completionRow,'The immutable response quote is the literal selectable source text');
  assert.equal(completionRow.unverifiedVisualCompletion,'Pump shall deliver 200 bar and be compatible with ISO 9001');
  assert.ok(completionRow.sourceReference.sourceText.includes('Pump shall deliver 200 bar'));
  const completionSheet=buildResponseSheet(completion.analysis);
  assert.equal(completionSheet.rows[0].values[3],'Pump shall deliver 200 bar');
  assert.ok(!completionSheet.rows[0].values[3].includes('ISO 9001'));
  assert.match(completion.analysis.reviewNote,/unverified suggestions and are not included in response rows or exports/);
  scenario='prose';
  const pdf=new jsPDF();
  quotes.forEach((quote,index)=>{if(index)pdf.addPage();pdf.text('Technical requirements',20,20);pdf.text(quote,20,40);if(index===4)pdf.text(recovery,20,60);});
  const result=await analyze(pdf);
  assert.equal(result.ok,true,result.error);
  const analysis=result.analysis;
  assert.equal(analysis.requirements.length,6);
  assert.deepEqual(analysis.requirements.map(row=>row.quote),[...quotes,recovery]);
  const recoveredRequirement=analysis.requirements.find(row=>row.quote===recovery);
  assert.equal(initialExtractionReturnedRecovery,false,'The first extraction pass deliberately omits this source requirement');
  assert.equal(omissionAuditReturnedRecovery,true,'A separate source-to-output audit discovers the omitted exact source quote');
  assert.ok(recoveredRequirement?.sourceReference.sourceText.replace(/\s+/g,' ').trim()===recovery,'The recovered requirement passes source verification');
  assert.ok(corruptedNumericClaimProposed,'The first pass deliberately proposes a mutated source value');
  for(const row of analysis.requirements){
    assert.equal(row.reviewed,false);
    assert.equal(row.sourceReference.locationPrecision,'exact');
    assert.equal(row.sourceReference.sourceText.replace(/\s+/g,' ').trim(),row.quote);
    assert.ok(row.bbox.width>0&&row.bbox.height>0);
    assert.equal(row.sourceReference.physicalPdfPageNumber,row.page);
    assert.equal(row.sourceReference.documentFingerprint,analysis.document.documentFingerprint);
  }
  assert.ok(analysis.rejectedSuggestionDetails.some(row=>row.reason==='source_quote_or_location_not_verified'));
  const rejectedCorruption=analysis.rejectedSuggestionDetails.find(row=>row.quotePreview.includes('999999 mbar.'));
  assert.equal(rejectedCorruption?.reason,'source_quote_or_location_not_verified','A corrupted numerical value is rejected at the source-grounding gate');
  assert.ok(analysis.requirements.some(row=>row.quote===quotes[1]),'The original source-backed numerical requirement remains intact');
  assert.ok(!analysis.requirements.some(row=>row.quote.includes('999999 mbar.')),'The corrupted claim never enters the response matrix');
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
  scenario='table-row-audit-gap';
  const tables=new jsPDF({unit:'pt',format:'a4'});
  for(let page=1;page<=2;page++){
    if(page>1)tables.addPage();
    if(page===1){tables.setFontSize(6);tables.rect(40,0,515,12);tables.text('Letterhead contact details',43,8);}
    const widths=page===1?[35,100,380]:[35,100,230,75,75];
    const sourceRows=[['A. Optical table',...widths.slice(1).map(()=>'')],['S. No.','Specification','Description',...(page===2?['Comply (Yes/No)','Remarks']:[])],
      ...(page===1?[['0','Unclear source row','Source layout cannot be resolved',...(page===2?['','']:[])]]:[]),
      ...Array.from({length:16},(_,index)=>[String(index+1),`Parameter ${index+1}`,`Required value ${index+1} mm${scenario==='table-row-audit-gap'&&index===0?'. Calibration report shall be supplied.':''}`,...(page===2?['','']:[])])];
    tables.setFontSize(11);tables.text(page===1?'Annexure I':'Annexure II',40,25);tables.text(page===1?'Technical Specifications for Optical Tables':'Technical Compliance Report for Optical Tables',40,45);
    tables.setFontSize(8);
    sourceRows.forEach((cells,row)=>{let x=40;cells.forEach((value,column)=>{tables.rect(x,70+row*26,widths[column],26);if(value)tables.text(value,x+3,85+row*26);x+=widths[column];});});
    if(page===1)tables.text(outsideTable,40,600);
  }
  tables.addPage();tables.text('Technical safety requirements',40,40);tables.text(quotes[2],40,70);
  const tableProgressStart = progressObservations.length;
  const mixed=await analyze(tables);
  assert.equal(mixed.ok,true,mixed.error);
  assert.deepEqual(progressObservations.slice(tableProgressStart).filter(event=>event.message==='Reading table rows and auditing independent requirements').map(event=>[event.current,event.total]),[[0,2],[2,2]],'Bounded mixed-layout vector processing reports completion after the page wave returns');
  const textAuditProgress=progressObservations.slice(tableProgressStart).filter(event=>event.message==='Checking routed technical text for omitted requirements');
  assert.ok(textAuditProgress.some(event=>event.stage==='coverage'&&event.current===0&&event.total>0),'Text-page completeness audit announces its active stage before waiting for the model');
  assert.equal(mixed.analysis.normalizedTables,true);
  const ambiguousSourceRow = mixed.analysis.coverage.pages[0].sourceTableCoverageRows.find(row=>row.cells.some(cell=>cell.includes('Unclear source row')));
  assert.ok(ambiguousSourceRow);
  assert.equal(ambiguousSourceRow.sourceClassification,'ambiguous');
  assert.equal(ambiguousSourceRow.classificationReason,'ambiguous_source_structure');
  assert.equal(ambiguousSourceRow.disposition,'unmapped');
  const auditedSourceRow = mixed.analysis.coverage.pages[0].sourceTableCoverageRows.find(row=>row.cells.some(cell=>cell.includes('Calibration report shall be supplied.')));
  assert.equal(auditedSourceRow?.semanticCoverageStatus,'possible_gap','possible semantic omission is surfaced on its detected source row');
  assert.match(auditedSourceRow?.semanticCoverageNote ?? '',/second independently assessable obligation/i);
  assert.equal(mixed.analysis.coverage.pages[0].sourceTableRowsNotShown,7,'audit states are retained for all rows even when the UI preview is capped');
  assert.deepEqual(ambiguousSourceRow.matchedRequirementIds,[],'Ambiguous source content stays out of output requirements and remains reviewable');
  assert.ok(mixed.analysis.requirements.some(row=>row.sourceSectionHeadings?.includes('Technical Specifications for Optical Tables')));
  assert.ok(mixed.analysis.requirements.some(row=>row.sourceSectionHeadings?.includes('Technical Compliance Report for Optical Tables')));
  const grouped=buildResponseSheet(mixed.analysis);
  assert.equal(grouped.rows.length,37,'Both tables, the recovered independent obligation, prose outside the grid, and the prose page retained');
  assert.equal(grouped.rows.filter(row=>row.values[7]==='Page 1').length,19);
  assert.equal(grouped.rows.filter(row=>row.values[7]==='Page 2').length,17);
  const projected=buildResponseSections(grouped);
  assert.deepEqual(projected.map(section=>section.rows.length),[2,17,17,1]);
  assert.equal(projected[0].annexure,'Annexure I');assert.equal(projected[2].annexure,'Annexure II');
  assert.ok(projected.every(section=>section.columns.every(column=>column.role!=='heading'&&column.role!=='page')));
  assert.equal(grouped.rows.filter(row=>row.values[0]==='A. Optical table').length,19);
  assert.ok(mixed.analysis.requirements.some(row=>row.quote===outsideTable&&row.sourceReference.locationPrecision==='exact'));
  assert.ok(!mixed.analysis.requirements.some(row=>row.quote.includes('Letterhead contact')));
  assert.ok(grouped.rows.every(row=>row.values[4]===''&&row.values[5]===''));
  assert.ok(grouped.rows.some(row=>row.values[3]===quotes[2]&&row.values[7]==='Page 3'));
  assert.ok(mixed.analysis.requirements.some(row=>row.quote==='Calibration report shall be supplied.' && row.reviewed===false && row.sourceReference.sourceText==='Calibration report shall be supplied.'),'an exact source excerpt from a possible-gap audit re-enters as an unchecked, source-verified recovery candidate');
  console.log(JSON.stringify({passed:true,cases:['zero-candidate extraction reports incompleteness without implying no requirements exist','zero-accepted run retains rejected-only diagnostics without creating requirements','model cannot assert source location or bypass technical filtering','verified cross-section conflict routes both cited pages and displays both source quotes','unsupported cross-section quote is rejected and leaves its pages uncertain','mixed bold heading retains assessable body','single-content source table preserved','independent vector tables run concurrently while headerless continuations inherit verified maps and audits remain source-ordered','bounded mixed-layout vector processing reports completed waves','text-page completeness audit announces its active stage','high-confidence visual completions remain unverified and out of exports','case-sensitive units retained','equal recovery quotes not duplicated','unsupported suggestions do not consume review capacity','verified response limit rejects without partial output','short unfamiliar clause','mixed schedule and prose','bounded five-page extraction','checker recovers deliberately omitted requirement','source validator rejects deliberately corrupted numeric value','vector-row semantic gap is surfaced without mutating extraction','invalid page rejection','exact source evidence','editable sheet with locked citations','different table schemas plus narrative page','16-row equipment grouping'],checkerMutationContract:{kind:'scripted provider contract, not a real-tender score',deliberatelyOmittedRequirements:1,omissionAuditRecovered:omissionAuditReturnedRecovery,recoveredQuoteGrounded:recoveredRequirement?.sourceReference.sourceText.replace(/\s+/g,' ').trim()===recovery,corruptedNumericClaims:1,corruptedClaimProposed:corruptedNumericClaimProposed,corruptedClaimRejected:rejectedCorruption?.reason==='source_quote_or_location_not_verified',originalNumericRequirementPreserved:analysis.requirements.some(row=>row.quote===quotes[1]),semanticGapSignalRecorded:auditedSourceRow?.semanticCoverageStatus==='possible_gap',realTenderQualityScore:null},routeCalls,extractionCalls}));
} finally {
  child.kill('SIGTERM');
  if(child.exitCode===null)await Promise.race([once(child,'exit'),new Promise(resolve=>setTimeout(resolve,3000))]);
  if(child.exitCode===null)child.kill('SIGKILL');
  provider.closeAllConnections();await new Promise(resolve=>provider.close(resolve));
}
