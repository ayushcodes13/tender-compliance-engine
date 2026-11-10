// Deterministic contract test: real PDF parsing/API/SSE/source validation/sheet edits,
// scripted provider responses. This does not measure the live model's recall.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import http from 'node:http';
import { once } from 'node:events';
import { spawn } from 'node:child_process';
import { mkdtemp, readdir, readFile, rm, unlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { jsPDF } from 'jspdf';
import { createCanvas, loadImage } from '@napi-rs/canvas';
import { buildResponseSections } from '../app/response-sections.ts';
import { buildResponseSheet, updateResponseSheetCell, removeResponseSheetRow } from '../app/response-sheet.ts';
import { consumeAnalysisStream } from '../app/analysis-events.ts';
import { isPopplerAvailable, isTesseractAvailable } from '../app/local-ocr.ts';

const quotes = [
  'Cryostat shall retain helium for 90 days.',
  'Vacuum shall remain below 0.000001 mbar.',
  'The bidder shall supply a 24 V controller.',
  'Firmware must support the OPC UA protocol.',
  'Ferromagnetic stainless steel.',
];
const recovery = 'Surface flatness shall be within 0.1 mm over 1 m square.';
const outsideTable = 'Service support shall remain available for 10 years.';
const selectedBlockOmission = 'Certificate shall be supplied.';
let scenario = "prose";
let failSixthBatchOnce = true;
let failPlannerTableOnce = true;
let failPlannerOcrOnce = true;
let failPlannerVisualOnce = true;
let failAdaptiveSecondWaveOnce = true;
let plannerTableClassificationCalls = 0;
let plannerOcrExtractionAttempts = 0;
let plannerVisualExtractionAttempts = 0;
let extractionCalls = 0;
let resumeGeneralRequestStarts = 0;
let routeCalls = 0;
let providerRequestCount = 0;
const providerSchemaCounts = new Map();
const plannerNativeRequestInputs = [];
const adaptivePlanInputs = [];
const plannerOcrRequestInputs = [];
const plannerVisualRequestInputs = [];
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
let activeRoutingRequests = 0;
let maximumRoutingConcurrency = 0;
const routingBatchEvents = [];
const vectorAuditPageOrder = [];
const vectorLabelEvents = [];
const progressObservations = [];
const forensicTraceDirectory = path.join(process.cwd(), '.local', 'forensic-traces');
const existingTraceFiles = new Set(await readdir(forensicTraceDirectory).catch(() => []));
const provider = http.createServer(async (request, response) => {
  providerRequestCount += 1;
  let trackedVectorLabelRequest = false;
  let trackedVectorLabelPage = 0;
  let trackedGeneralExtractionRequest = false;
  let trackedGeneralExtractionFirstPage = 0;
  let trackedRoutingRequest = false;
  let trackedRoutingGroup = 0;
  try {
    let raw = '';
    for await (const chunk of request) raw += chunk;
    const body = JSON.parse(raw);
    const schema = body.response_format?.json_schema?.name;
    providerSchemaCounts.set(schema, (providerSchemaCounts.get(schema) ?? 0) + 1);
    if (schema === 'tender_requirements' && scenario === 'planner-ocr-resume') plannerOcrExtractionAttempts += 1;
    if (schema === 'visual_table_row_labels' && scenario === 'planner-table-resume') plannerTableClassificationCalls += 1;
    if (scenario === 'route-batch-concurrency' && schema === 'technical_section_route') {
      trackedRoutingRequest = true;
      activeRoutingRequests += 1;
      maximumRoutingConcurrency = Math.max(maximumRoutingConcurrency, activeRoutingRequests);
      trackedRoutingGroup = Number(raw.match(/page group (\d+) of/)?.[1] ?? 0);
      routingBatchEvents.push({ group: trackedRoutingGroup, event: 'started', at: Date.now() });
      await new Promise(resolve => setTimeout(resolve, trackedRoutingGroup === 1 ? 220 : 50));
    }
    if (scenario === 'slow-general-extraction' && schema === 'tender_requirements') await new Promise(resolve => setTimeout(resolve, 150));
    if (scenario === 'resume-general-extraction' && schema === 'tender_requirements') {
      resumeGeneralRequestStarts += 1;
      const batchPages = [...new Set([...raw.matchAll(/PDF PAGE (\d+)/g)].map(match => Number(match[1])))];
      await new Promise(resolve => setTimeout(resolve, batchPages[0] === 1 ? 60 : 400));
    }
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
    if (['vector-page-concurrency', 'vector-page-straggler'].includes(scenario) && schema === 'visual_table_row_labels') {
      trackedVectorLabelRequest = true;
      activeVectorLabelRequests += 1;
      vectorLabelRequestCount += 1;
      maximumVectorLabelConcurrency = Math.max(maximumVectorLabelConcurrency, activeVectorLabelRequests);
      trackedVectorLabelPage = Number([...raw.matchAll(/Rendered PDF page (\d+)/g)].at(-1)?.[1] ?? 0);
      vectorLabelEvents.push({ page: trackedVectorLabelPage, event: 'started', at: Date.now() });
      const delay = scenario === 'vector-page-straggler' ? (trackedVectorLabelPage === 2 ? 800 : 40) : 100;
      await new Promise(resolve => setTimeout(resolve, delay));
    }
    if (scenario === 'vector-page-concurrency' && schema === 'source_row_semantic_coverage') {
      const auditInput = body.messages.at(-1)?.content ?? '';
      const pageMatch = auditInput.match(/Maximum load on unit (\d+)/);
      if (pageMatch) vectorAuditPageOrder.push(Number(pageMatch[1]));
    }
    const contents = body.messages.flatMap(message => typeof message.content === 'string' ? [{type:'text',text:message.content}] : message.content);
    const text = contents.filter(item=>item.type==='text').map(item=>item.text).join('\n');
    if (schema === 'tender_requirements' && scenario === 'planner-visual-region' && /Parser image region ID:/i.test(text)) {
      plannerVisualExtractionAttempts += 1;
      const images = contents.filter(item => item.type === 'image_url');
      const sizes = await Promise.all(images.map(async item => {
        const image = await loadImage(Buffer.from(item.image_url.url.split(',')[1], 'base64'));
        return { width: image.width, height: image.height };
      }));
      plannerVisualRequestInputs.push({ text, imageCount: images.length, sizes });
    }
    if (['planner-native-text','planner-native-empty','planner-native-resume','adaptive-two-rounds'].includes(scenario) && schema === 'tender_requirements') plannerNativeRequestInputs.push({ scenario, text, imageCount: contents.filter(item=>item.type==='image_url').length });
    if (schema === 'technical_table_page_batch_rows' || schema === 'technical_table_missing_rows') visualBatchObservations.push({scenario,schema,imageCount:contents.filter(item=>item.type==='image_url').length});
    for (const item of contents.filter(item=>item.type==='image_url')) assert.match(item.image_url.url, /^data:image\/jpeg;base64,[A-Za-z0-9+/]+=*$/);
    let result;
    if (schema === 'visual_table_row_labels' && scenario === 'planner-table-resume' && failPlannerTableOnce) {
      failPlannerTableOnce = false;
      response.destroy();
      return;
    }
    if (schema === 'tender_requirements' && scenario === 'planner-ocr-resume' && failPlannerOcrOnce) {
      failPlannerOcrOnce = false;
      response.destroy();
      return;
    }
    if (schema === 'tender_requirements' && scenario === 'planner-visual-region' && /Parser image region ID:/i.test(text) && failPlannerVisualOnce) {
      failPlannerVisualOnce = false;
      response.destroy();
      return;
    }
    if (schema === 'tender_task_plan') {
      const planInput = JSON.parse(body.messages.at(-1)?.content ?? '{}');
      const sourceIds = planInput.pages.map(page => page.sourceId);
      const planScope = sourceIds.map(sourceId => {
        const page = planInput.pages.find(item => item.sourceId === sourceId);
        const proposedExclusion = scenario === 'planner-exclusion-conflict' && page.physicalPage === 1;
        return { sourceIds: [sourceId], disposition: proposedExclusion ? 'outside_task' : 'relevant', rationale: proposedExclusion ? 'Fixture proposes that this page is outside the task.' : 'Scripted fixture routes this source page for technical review.' };
      });
      const inScopeIds = planScope.filter(scope => scope.disposition !== 'outside_task').flatMap(scope => scope.sourceIds);
      const firstNativeTextId = planInput.pages.flatMap(page => page.regions.filter(region => region.kind === 'native_text_block').map(region => region.sourceId))[0];
      const firstTableId = planInput.pages.flatMap(page => page.regions.filter(region => region.kind === 'table').map(region => region.sourceId))[0];
      const firstOcrId = planInput.pages.flatMap(page => page.regions.filter(region => region.kind.startsWith('ocr_')).map(region => region.sourceId))[0];
      const firstImageId = planInput.pages.flatMap(page => page.regions.filter(region => region.kind.startsWith('image_')).map(region => region.sourceId))[0];
      const nativeTextIds = planInput.pages.flatMap(page => page.regions.filter(region => region.kind === 'native_text_block').map(region => region.sourceId));
      const plannerNativeScenario = ['planner-native-text','planner-native-empty','planner-native-resume','adaptive-two-rounds'].includes(scenario);
      const plannerTableScenario = scenario === 'planner-table-resume';
      const plannerOcrScenario = scenario === 'planner-ocr-resume';
      const plannerVisualScenario = scenario === 'planner-visual-region';
      const actions = scenario !== 'adaptive-two-rounds' && planInput.planningRound > 0
        ? []
        : scenario === 'adaptive-two-rounds'
        ? planInput.planningRound === 0
          ? (firstNativeTextId ? [{ mode: 'native_text', sourceIds: [firstNativeTextId], rationale: 'Inspect the first native text block.' }] : [])
          : planInput.planningRound === 1
            ? (() => { const completed = new Set(planInput.priorOutcomes.filter(item => item.status === 'executed').flatMap(item => item.sourceIds)); const nextId = nativeTextIds.find(id => !completed.has(id)); return nextId ? [{ mode: 'native_text', sourceIds: [nextId], rationale: `Inspect this different parser block after reviewing: ${planInput.priorOutcomes.map(item => item.summary).join(' | ')}` }] : []; })()
            : []
        : plannerTableScenario
        ? (firstTableId ? [{ mode: 'table', sourceIds: [firstTableId], rationale: 'Inspect the parser-owned vector table.' }] : [])
        : plannerOcrScenario
        ? (firstOcrId ? [{ mode: 'ocr', sourceIds: [firstOcrId], rationale: 'Extract the selected parser-owned OCR transcript.' }] : [])
        : plannerVisualScenario
        ? (firstImageId ? [{ mode: 'visual', sourceIds: [firstImageId], rationale: 'Inspect the selected parser-owned visual crop.' }] : [])
        : plannerNativeScenario
        ? (firstNativeTextId ? [{ mode: 'native_text', sourceIds: [firstNativeTextId], rationale: 'Inspect the first parser text block.' }] : [])
        : Array.from({ length: Math.ceil(inScopeIds.length / 12) }, (_, index) => ({
          mode: 'native_text', sourceIds: inScopeIds.slice(index * 12, (index + 1) * 12), rationale: 'Inspect the supplied source text.'
        }));
      result = {
        schemaVersion: 1,
        runId: planInput.runId,
        sourceFingerprint: planInput.sourceFingerprint,
        proposal: {
          decision: actions.length ? 'continue' : 'stop',
          decisionRationale: actions.length ? 'Parser-owned sources remain available for bounded inspection.' : 'No further supported inspection is available in this fixture.',
          task: planInput.task,
          scope: planScope,
          sections: plannerNativeScenario && firstNativeTextId
            ? [{ label: 'Technical source', sourceIds: [firstNativeTextId] }]
            : inScopeIds.length ? [{ label: 'Technical source', sourceIds: inScopeIds }] : [],
          actions,
          openQuestions: [],
        },
      };
      if (scenario === 'adaptive-two-rounds') adaptivePlanInputs.push(planInput);
    } else if (schema === 'technical_section_route') {
      routeCalls++;
      const pages = [...new Set([...text.matchAll(/PDF PAGE (\d+)/g)].map(match=>Number(match[1])))];
      result = {sections:['page-disposition-only','possibly-relevant-page','unrouted-page'].includes(scenario)?[]:pages.map(page=>({title:'Technical source',start_page:page,end_page:page,section_type:scenario==='unlocated-remark'||scenario==='page-batched-fallback'||page===2?'compliance_schedule':'technical_requirements',reason:'Fixture source'})),uncertain_pages:scenario==='possibly-relevant-page'?pages:[],page_dispositions:scenario==='unrouted-page'?[]:pages.map(page=>({page,classification:scenario==='possibly-relevant-page'?'possibly_relevant':'relevant',reason:scenario==='possibly-relevant-page'?'The page excerpt is ambiguous and may contain technical obligations.':'Fixture source contains a technical test case.'})),routing_warnings:[],possible_source_conflicts:scenario==='cross-section-conflict'?[{page_a:1,quote_a:'X-Band EPR spectrometer system',page_b:2,quote_b:'Advanced Spectrofluorometer',reason:'The two supplied sections identify different equipment subjects.'}]:scenario==='unsupported-section-conflict'?[{page_a:1,quote_a:'X-Band EPR spectrometer system',page_b:2,quote_b:'EPR spectrometer',reason:'The two supplied sections identify different equipment subjects.'}]:[]};
    } else if (schema === 'tender_source_column_map' || schema === 'visual_table_row_labels') {
      const page = Number([...text.matchAll(/(?:begins on PDF page|Rendered PDF page) (\d+)/g)].at(-1)?.[1]);
      const independentVectorColumns = scenario === 'vector-page-concurrency' ? [
        [{header:'Technical Parameters NIQ',role:'heading'},{header:'Remark',role:'remark'}],
        [],
        [{header:'S. No.',role:'serial'},{header:'Parameter',role:'heading'},{header:'Specification',role:'specification'}],
      ][page - 1] : scenario === 'vector-page-straggler'
        ? page === 1 ? [{header:'Technical Parameters NIQ',role:'heading'},{header:'Remark',role:'remark'}]
          : page === 2 ? []
            : [{header:'S. No.',role:'serial'},{header:'Parameter',role:'heading'},{header:'Specification',role:'specification'}]
        : null;
      const columns = independentVectorColumns ?? (['single-content','planner-table-resume','mixed-native-heading','visual-completion'].includes(scenario) ? [{header:'Technical Parameters NIQ',role:'heading'},{header:'Remark',role:'remark'}] : [{header:'S. No.',role:'serial'},{header:'Specification',role:'heading'},{header:'Description',role:'specification'},
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
      const duplicateQuote='The centrifuge shall accommodate 10 samples.';
      result={columns:[],requirements:scenario==='page-batched-fallback'&&text.includes(duplicateQuote)?[{page:1,quote:duplicateQuote,visual_region_index:0,row_type:'requirement',category:'Performance',heading_prefix:'',remark:'',display_lines:[duplicateQuote],continues_previous:false}]:[]};
    } else if (schema === 'source_row_semantic_coverage') {
      const rows = JSON.parse(body.messages.at(-1)?.content ?? '[]');
      if (scenario === 'vector-page-straggler') {
        const pageMatch = JSON.stringify(rows).match(/Maximum load on unit (\d+)/);
        if (pageMatch) vectorAuditPageOrder.push(Number(pageMatch[1]));
      }
      result = { rows: rows.map(row => row.source_cells.some(cell => cell.includes('Calibration report shall be supplied.'))
        ? { row_index: row.row_index, status: 'possible_gap', note: 'The source row contains a second independently assessable obligation.', missing_source_quotes: ['Calibration report shall be supplied.'] }
        : { row_index: row.row_index, status: 'no_gap_reported', note: '', missing_source_quotes: [] }) };
    } else if (schema === 'technical_text_missing_requirements') {
      const requirements=[
        ...(text.includes(recovery)?[{page:5,quote:recovery,category:'Performance',row_type:'requirement',heading_prefix:''}]:[]),
        ...(scenario==='planner-native-text'&&text.includes(selectedBlockOmission)?[{page:1,quote:selectedBlockOmission,category:'Documentation',row_type:'requirement',heading_prefix:''}]:[]),
        ...(text.includes(outsideTable)?[{page:1,quote:outsideTable,category:'Other',row_type:'requirement',heading_prefix:''},{page:1,quote:'Required value 1 mm',category:'Other',row_type:'requirement',heading_prefix:''},{page:1,quote:'A. Optical table',category:'Other',row_type:'section',heading_prefix:''}]:[]),
      ];
      if(scenario==='prose'&&requirements.some(item=>item.quote===recovery))omissionAuditReturnedRecovery=true;
      result = {columns:[],requirements};
    } else if (schema === 'tender_requirements') {
      extractionCalls++;
      const pages = [...new Set([...text.matchAll(/PDF PAGE (\d+)/g)].map(match=>Number(match[1])))];
      if (scenario === 'planner-ocr-resume') plannerOcrRequestInputs.push(text);
      if (scenario === 'adaptive-two-rounds' && text.includes(quotes[1]) && failAdaptiveSecondWaveOnce) {
        failAdaptiveSecondWaveOnce = false;
        response.destroy();
        return;
      }
      if (scenario === 'planner-native-resume' && plannerNativeRequestInputs.filter(item => item.scenario === scenario).length === 1) {
        response.destroy();
        return;
      }
      const failSixthBatch = scenario === 'partial-general-batch-six-of-six' && pages[0] === 16 && failSixthBatchOnce;
      if (failSixthBatch) failSixthBatchOnce = false;
      if (['partial-general-batch', 'partial-general-batch-six-of-six', 'all-general-batches-fail'].includes(scenario)
        && (scenario === 'all-general-batches-fail'
          || (scenario === 'partial-general-batch' && pages[0] === 10)
          || failSixthBatch)) {
        response.destroy();
        return;
      }
      const requirements=quotes.flatMap((quote,index)=>text.includes(quote)&&pages.includes(index+1)?[{page:index+1,quote,category:'Other',row_type:'requirement',heading_prefix:''}]:[]);
      result={columns:[],requirements:[...requirements,...(scenario==='prose'&&pages.includes(2)?[{page:2,quote:'Vacuum shall remain below 999999 mbar.',row_type:'requirement',category:'Other',heading_prefix:''}]:[]),{page:pages[0],quote:'Invented limit of 999999 kN.',row_type:'requirement',category:'Other',heading_prefix:''},{page:999,quote:quotes[0],row_type:'requirement',category:'Other',heading_prefix:''}]};
      if (scenario === 'adaptive-two-rounds') {
        const quote = quotes.find(candidate => text.includes(candidate));
        result = { columns: [], requirements: quote ? [{ page: 1, quote, category: 'Performance', row_type: 'requirement', heading_prefix: '' }] : [] };
      }
      if (scenario === 'planner-ocr-resume') {
        const quote = text.match(/PDF PAGE 1\n([^\n]+)/)?.[1]?.trim() ?? '';
        result = { columns: [], requirements: quote ? [{ page: 1, quote, category: 'Performance', row_type: 'requirement', heading_prefix: '' }] : [] };
      }
      if (scenario === 'planner-visual-region') {
        result = { columns: [], requirements: [{ page: 1, quote: 'Pressure shall remain below 2 Pa.', category: 'Performance', row_type: 'requirement', heading_prefix: '' }] };
      }
      if (scenario === 'planner-native-empty' && plannerNativeRequestInputs.filter(item => item.scenario === scenario).length === 1) result={columns:[],requirements:[]};
      if(scenario==='prose'&&result.requirements.some(item=>item.quote==='Vacuum shall remain below 999999 mbar.'))corruptedNumericClaimProposed=true;
      if(scenario==='prose'&&result.requirements.some(item=>item.quote===recovery))initialExtractionReturnedRecovery=true;
      if(scenario==='all-rejected')result={columns:[],requirements:Array.from({length:60},(_,index)=>({page:pages[0],quote:`Invented limit ${index} of 999999 kN.`,row_type:'requirement',category:'Other',heading_prefix:''}))};
      if(scenario==='no-candidates')result={columns:[],requirements:[]};
      if(scenario==='injected-metadata')result.requirements=[{page:1,quote:quotes[0],row_type:'requirement',category:'Other',heading_prefix:'',sourceBox:{x:0,y:0,width:1,height:1},source_cells_exact:true,source_row_index:999,source_column_index:0,visualOcr:true},{page:1,quote:'The catalog shall specify ingress protection IP67.',row_type:'requirement',category:'Documentation',heading_prefix:''},{page:1,quote:'Payment terms are 30 days.',row_type:'instruction',category:'Other',heading_prefix:'',source_cells_exact:true}];
      if(scenario==='case-sensitive')result={columns:[],requirements:[...text.matchAll(/Optical power shall be 1 (?:mW|MW)\./g)].map(match=>({page:1,quote:match[0],category:'Other',row_type:'requirement',heading_prefix:''}))};
      if(scenario==='invalid-capacity')result.requirements.push(...Array.from({length:300},(_,index)=>({page:1,quote:`Invented unsupported parameter ${index}.`,row_type:'requirement',category:'Other',heading_prefix:''})));
      if(scenario==='verified-capacity')result={columns:[],requirements:[...text.matchAll(/Capacity parameter (\d+) shall be (\d+) mm\./g)].map(match=>({page:Math.floor((Number(match[1])-1)/50)+1,quote:match[0],category:'Other',row_type:'requirement',heading_prefix:''}))};
      if(scenario==='invalid-extraction-shape')result={columns:[]};
    } else throw new Error(`Unexpected provider operation: ${schema}`);
    response.writeHead(200, {'content-type':'application/json'});
    response.end(JSON.stringify({choices:[{message:{content:JSON.stringify(result)}}]}));
  } catch(error) {response.writeHead(500);response.end(JSON.stringify({error:String(error)}));}
  finally {
    if (trackedRoutingRequest) {
      routingBatchEvents.push({ group: trackedRoutingGroup, event: 'completed', at: Date.now() });
      activeRoutingRequests -= 1;
    }
    if (trackedGeneralExtractionRequest) {
      generalExtractionBatchEvents.push({ firstPage: trackedGeneralExtractionFirstPage, event: 'completed', at: Date.now() });
    }
    if (trackedVectorLabelRequest) activeVectorLabelRequests -= 1;
    if (trackedVectorLabelRequest) vectorLabelEvents.push({ page: trackedVectorLabelPage, event: 'completed', at: Date.now() });
    if (trackedGeneralExtractionRequest) activeGeneralExtractionRequests -= 1;
  }
});
provider.listen(0,'127.0.0.1'); await once(provider,'listening');
const runStoreDirectory = await mkdtemp(path.join(tmpdir(), 'tce-pipeline-run-store-'));
const portProbe=http.createServer();portProbe.listen(0,'127.0.0.1');await once(portProbe,'listening');const appPort=portProbe.address().port;await new Promise(resolve=>portProbe.close(resolve));
const base=`http://127.0.0.1:${appPort}`;
const appOptions={
  cwd:process.cwd(),env:{...process.env,OPENAI_API_KEY:'fixture-only-key',OPENAI_BASE_URL:`http://127.0.0.1:${provider.address().port}`,OPENAI_MODEL:'gpt-6-luna',APP_ACCESS_PASSWORD:'fixture-only-password',MAX_FILE_BYTES:String(1024 * 1024),TCE_FORENSIC_TRACE:'1',TCE_MODEL_TIMING:'1',TCE_RUN_STORE_KEY:'ab'.repeat(32),TCE_RUN_STORE_PATH:path.join(runStoreDirectory,'runs.sqlite')},stdio:['ignore','pipe','pipe'],
};
let logs='';
let child;
function launchApp() {
  child=spawn(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',String(appPort)],appOptions);
  child.stdout.on('data',chunk=>{logs+=chunk;});
  child.stderr.on('data',chunk=>{logs+=chunk;});
}
async function waitForApp() {
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
}
async function restartApp() {
  child.kill('SIGTERM');
  if(child.exitCode===null) await Promise.race([once(child,'exit'),new Promise(resolve=>setTimeout(resolve,3000))]);
  if(child.exitCode===null) { child.kill('SIGKILL'); await once(child,'exit'); }
  launchApp();
  await waitForApp();
}
launchApp();
try {
  await waitForApp();
  const unauthenticatedPage = await fetch(base);
  assert.equal(unauthenticatedPage.status, 401, 'The application UI rejects anonymous requests');
  const unauthenticated = await fetch(`${base}/api/analyze`, { method: 'POST', body: new FormData() });
  assert.equal(unauthenticated.status, 401, 'The upload endpoint rejects anonymous requests before parsing or analysis');
  assert.match(unauthenticated.headers.get('www-authenticate') ?? '', /^Basic /);
  const authHeader = `Basic ${Buffer.from('tender:fixture-only-password').toString('base64')}`;
  const providerCountBeforeMalformed = providerRequestCount;
  const malformed = await fetch(`${base}/api/analyze`, {
    method: 'POST',
    headers: { authorization: authHeader, 'content-type': 'text/plain' },
    body: 'not a multipart form',
  });
  assert.equal(malformed.status, 400, 'Malformed form bodies are rejected before analysis starts');
  assert.deepEqual(await malformed.json(), { error: 'The uploaded form could not be read.' });
  assert.equal(providerRequestCount, providerCountBeforeMalformed, 'Malformed forms initiate no model requests');
  const oversizedForm = new FormData();
  oversizedForm.set('file', new File([new Uint8Array(2 * 1024 * 1024)], 'oversized.pdf', { type: 'application/pdf' }));
  const oversized = await fetch(`${base}/api/analyze`, { method: 'POST', headers: { authorization: authHeader }, body: oversizedForm });
  assert.equal(oversized.status, 413, 'Multipart bodies larger than the configured request cap receive HTTP 413');
  assert.deepEqual(await oversized.json(), { error: 'The uploaded request exceeds the configured size limit.' });
  assert.equal(providerRequestCount, providerCountBeforeMalformed, 'Oversized bodies initiate no model requests');
  async function analyze(pdf, options = {}) {
    const body=new FormData();body.set('file',new File([pdf.output('arraybuffer')],'synthetic-tender.pdf',{type:'application/pdf'}));
    if (options.resumeRunId) body.set('resumeRunId', options.resumeRunId);
    const controller = new AbortController();
    const response = await fetch(base+'/api/analyze',{method:'POST',body,headers:{authorization:authHeader},signal:controller.signal});
    assert.match(response.headers.get('cache-control') ?? '', /private, no-store/, `${scenario} returned HTTP ${response.status}: ${logs.slice(-2500)}`);
    return consumeAnalysisStream(response,{signal:controller.signal,onProgress:(progress)=>{
      progressObservations.push({scenario, ...progress});
      options.onProgress?.(progress);
      if (options.stopAt?.(progress)) controller.abort('scripted interruption after checkpoint');
    }});
  }
  const short=new jsPDF();short.text(quotes[0],20,30);
  const one=await analyze(short);
  assert.equal(one.ok,true,one.error);
  assert.equal(one.analysis.document.documentFingerprint,createHash('sha256').update(Buffer.from(short.output('arraybuffer'))).digest('hex'));
  assert.equal(one.analysis.document.inventoryIntegrity,'structurally-verified');
  assert.equal(one.analysis.requirements.length,1);
  assert.equal(one.analysis.requirements[0].quote,quotes[0]);
  assert.ok(providerRequestCount > providerCountBeforeMalformed, 'A valid upload continues into the scripted model analysis path');
  scenario='planner-native-text';
  const plannerSlice = new jsPDF();
  plannerSlice.setFontSize(6);
  plannerSlice.text(`${quotes[0]} ${selectedBlockOmission}`,20,30);
  plannerSlice.text(outsideTable,20,50);
  const plannedSliceResult = await analyze(plannerSlice);
  assert.equal(plannedSliceResult.ok,true,plannedSliceResult.error);
  const plannedBlockId = plannedSliceResult.analysis.coverage.plannedInspections.find(item => item.mode === 'native_text')?.sourceId;
  assert.ok(plannedBlockId?.includes(':text:'),'The planner should identify a parser-owned native text block');
  assert.ok(plannedSliceResult.analysis.coverage.plannedInspections.some(item => item.sourceId === plannedBlockId && item.state === 'executed'));
  assert.ok(plannedSliceResult.analysis.requirements.some(row => row.quote === quotes[0] && row.sourceReference.sourceElementIds.includes(plannedBlockId)),'The selected block output retains its exact source-element link');
  assert.ok(plannedSliceResult.analysis.requirements.some(row => row.quote === selectedBlockOmission && row.sourceReference.sourceText === selectedBlockOmission)
    || plannedSliceResult.analysis.classificationReviewCandidates?.some(candidate => candidate.quote === selectedBlockOmission),
    'A source-grounded omission from a planner-executed block remains visible in requirements or classification review');
  assert.ok(plannedSliceResult.analysis.requirements.some(row => row.quote === outsideTable),'The unselected same-page block remains available to the legacy fallback');
  assert.ok(plannerNativeRequestInputs.length >= 2,'The selected block and remaining fallback text use distinct extraction calls');
  assert.ok(plannerNativeRequestInputs[0].text.includes(quotes[0]));
  assert.ok(!plannerNativeRequestInputs[0].text.includes(outsideTable),'The planner handler receives only the selected native block');
  assert.equal(plannerNativeRequestInputs[0].imageCount,0,'The native-text handler does not receive page images');
  assert.ok(plannerNativeRequestInputs[1].text.includes(outsideTable));
  assert.ok(!plannerNativeRequestInputs[1].text.includes(quotes[0]),'The fallback does not re-send successfully executed source text');
  scenario='adaptive-two-rounds';
  const adaptivePdf = new jsPDF();
  adaptivePdf.setFontSize(6);
  adaptivePdf.text(quotes[0],20,30);
  adaptivePdf.text(quotes[1],20,50);
  adaptivePdf.text(outsideTable,20,70);
  const plannerCallCountBeforeAdaptive = providerSchemaCounts.get('tender_task_plan') ?? 0;
  let adaptiveRunId = null;
  const interruptedAdaptiveResult = await analyze(adaptivePdf,{onProgress:progress=>{if(progress.resumable&&progress.runId)adaptiveRunId=progress.runId;}});
  assert.equal(interruptedAdaptiveResult.ok,true,interruptedAdaptiveResult.error);
  assert.equal(interruptedAdaptiveResult.resumable,true,'A provider interruption during the second adaptive work wave pauses the partial run for resume');
  assert.match(adaptiveRunId??'',/^run_[a-f0-9]{32}$/i);
  assert.equal(adaptivePlanInputs.length,2,'The first result is fed to the second planner decision before the second work wave starts');
  assert.ok(adaptivePlanInputs[1].priorOutcomes.some(item=>item.summary.includes(quotes[0])));
  await restartApp();
  const adaptiveResult = await analyze(adaptivePdf,{resumeRunId:adaptiveRunId});
  assert.equal(adaptiveResult.ok,true,adaptiveResult.error);
  assert.equal(adaptivePlanInputs.length,3);
  assert.equal(providerSchemaCounts.get('tender_task_plan') ?? 0,plannerCallCountBeforeAdaptive + 3,'Resume reuses both saved decisions, then plans a final stop after the recovered second wave');
  assert.equal(failAdaptiveSecondWaveOnce,false,'The synthetic interruption happened during the newly selected second work wave');
  assert.equal(adaptivePlanInputs[0].planningRound,0);
  assert.equal(adaptivePlanInputs[1].planningRound,1);
  assert.ok(adaptivePlanInputs[1].priorOutcomes.some(item => item.summary.includes(quotes[0])),'The second decision receives the first wave\'s literal source-validated outcome');
  const firstAdaptiveSource = adaptivePlanInputs[0].pages.flatMap(page => page.regions).find(region => region.kind === 'native_text_block')?.sourceId;
  const secondAdaptiveSource = adaptivePlanInputs[1].pages.flatMap(page => page.regions).find(region => region.kind === 'native_text_block' && !adaptivePlanInputs[1].priorOutcomes.some(item => item.sourceIds.includes(region.sourceId)))?.sourceId;
  assert.notEqual(secondAdaptiveSource,firstAdaptiveSource,'The adaptive plan selects a different parser-owned block after seeing the first outcome');
  assert.ok(adaptivePlanInputs[2].planningRound === 2 && adaptivePlanInputs[2].priorOutcomes.some(item => item.summary.includes(quotes[0])) && adaptivePlanInputs[2].priorOutcomes.some(item => item.summary.includes(quotes[1])),'The third decision sees cumulative grounded outcomes from both waves and returns stop');
  assert.ok(adaptiveResult.analysis.requirements.some(row => row.quote === quotes[0]));
  assert.ok(adaptiveResult.analysis.requirements.some(row => row.quote === quotes[1]));
  const adaptiveCoverage = adaptiveResult.analysis.coverage.plannedInspections.filter(item => item.mode === 'native_text');
  assert.ok(adaptiveCoverage.length >= 2 && adaptiveCoverage.every(item => item.state === 'executed'));
  const adaptiveNativeInputs = plannerNativeRequestInputs.filter(item=>item.scenario==='adaptive-two-rounds');
  assert.equal(adaptiveNativeInputs.length,4,'Resume retries only the unfinished second block, then fallback sees only the remaining block');
  assert.ok(adaptiveNativeInputs[0].text.includes(quotes[0]));
  assert.ok(adaptiveNativeInputs[1].text.includes(quotes[1])&&adaptiveNativeInputs[2].text.includes(quotes[1]));
  assert.ok(adaptiveNativeInputs[2].text.includes(outsideTable)&&adaptiveNativeInputs[2].text.includes(quotes[1])&&!adaptiveNativeInputs[2].text.includes(quotes[0]),'Fallback may inspect the failed block but must not repeat the already completed first block');
  assert.ok(adaptiveNativeInputs[3].text.includes(quotes[1])&&!adaptiveNativeInputs[3].text.includes(quotes[0]),'Resume retries the unfinished second block without repeating the completed first block');
  scenario='planner-native-empty';
  const emptyPlannerSlice = new jsPDF();
  emptyPlannerSlice.text(quotes[0],20,30);
  const emptyPlannerResult = await analyze(emptyPlannerSlice);
  assert.equal(emptyPlannerResult.ok,true,emptyPlannerResult.error);
  assert.ok(emptyPlannerResult.analysis.requirements.some(row => row.quote === quotes[0]),'A valid but empty planner result does not suppress legacy fallback');
  assert.ok(emptyPlannerResult.analysis.coverage.plannedInspections.some(item => item.mode === 'native_text' && item.state === 'deferred_to_legacy'));
  const emptyPlannerInputs = plannerNativeRequestInputs.filter(item => item.scenario === 'planner-native-empty');
  assert.equal(emptyPlannerInputs.length,2,'The empty planned result is followed by the legacy fallback request');
  assert.ok(emptyPlannerInputs.every(item => item.text.includes(quotes[0])));
  scenario='planner-native-resume';
  const plannerResumePdf = new jsPDF();
  plannerResumePdf.text(quotes[0],20,30);
  plannerResumePdf.text(outsideTable,20,50);
  let plannerResumeRunId = null;
  const plannerCallsBeforeResumeFailure = providerSchemaCounts.get('tender_task_plan') ?? 0;
  const routeCallsBeforeResumeFailure = providerSchemaCounts.get('technical_section_route') ?? 0;
  const failedPlannerRun = await analyze(plannerResumePdf, {
    onProgress: progress => { if (progress.resumable && progress.runId) plannerResumeRunId = progress.runId; },
  });
  assert.equal(failedPlannerRun.ok,false,'A provider interruption leaves the planner-selected source operation retryable');
  assert.match(plannerResumeRunId ?? '', /^run_[a-f0-9]{32}$/i, 'The planner operation has a resumable run handle after its plan and unit state are checkpointed');
  assert.equal(plannerNativeRequestInputs.filter(item => item.scenario === scenario).length,1,'The interrupted run stopped on its first planner-selected extraction request');
  await restartApp();
  const resumedPlannerRun = await analyze(plannerResumePdf,{resumeRunId:plannerResumeRunId});
  assert.equal(resumedPlannerRun.ok,true,resumedPlannerRun.error);
  assert.equal(providerSchemaCounts.get('tender_task_plan') ?? 0,plannerCallsBeforeResumeFailure + 2,'Resume reuses the first plan, then requests a bounded decision after the recovered source result');
  assert.equal(providerSchemaCounts.get('technical_section_route') ?? 0,routeCallsBeforeResumeFailure + 1,'Planner resume reuses the completed page-routing artifact');
  const plannerResumeInputs = plannerNativeRequestInputs.filter(item => item.scenario === scenario);
  assert.equal(plannerResumeInputs.length,3,'Resume retries the failed planner unit, then runs the unselected legacy fallback once');
  assert.ok(plannerResumeInputs[0].text.includes(quotes[0]) && !plannerResumeInputs[0].text.includes(outsideTable));
  assert.ok(plannerResumeInputs[1].text.includes(quotes[0]) && !plannerResumeInputs[1].text.includes(outsideTable),'The failed planner-selected unit is retried with the same source-bound input');
  assert.ok(plannerResumeInputs[2].text.includes(outsideTable) && !plannerResumeInputs[2].text.includes(quotes[0]),'The successfully resumed planner block is not duplicated in legacy fallback');
  const resumedPlannerBlockId = resumedPlannerRun.analysis.coverage.plannedInspections.find(item => item.mode === 'native_text')?.sourceId;
  assert.ok(resumedPlannerBlockId?.includes(':text:'));
  assert.ok(resumedPlannerRun.analysis.coverage.plannedInspections.some(item => item.sourceId === resumedPlannerBlockId && item.state === 'executed'));
  assert.ok(resumedPlannerRun.analysis.requirements.some(row => row.quote === quotes[0] && row.sourceReference.sourceElementIds.includes(resumedPlannerBlockId)),'A resumed planner result retains its exact selected parser source');
  scenario='resume-path';
  let interruptedRunId = null;
  const plannerCallsBeforeInterrupt = providerSchemaCounts.get('tender_task_plan') ?? 0;
  const routeCallsBeforeInterrupt = providerSchemaCounts.get('technical_section_route') ?? 0;
  await assert.rejects(analyze(short, {
    stopAt: progress => progress.message === 'Requesting technical extraction batches 1–1 of 1',
    onProgress: progress => { if (progress.resumable && progress.runId) interruptedRunId = progress.runId; },
  }), /scripted interruption|cancelled|aborted/i);
  assert.match(interruptedRunId ?? '', /^run_[a-f0-9]{32}$/i, 'The stream exposes a resumable run handle only after it has been checkpointed');
  const plannerCallsAfterInterrupt = providerSchemaCounts.get('tender_task_plan') ?? 0;
  const routeCallsAfterInterrupt = providerSchemaCounts.get('technical_section_route') ?? 0;
  assert.equal(plannerCallsAfterInterrupt, plannerCallsBeforeInterrupt + 1);
  assert.equal(routeCallsAfterInterrupt, routeCallsBeforeInterrupt + 1);
  await restartApp();
  const resumed = await analyze(short, { resumeRunId: interruptedRunId });
  assert.equal(resumed.ok, true, resumed.error);
  assert.equal(providerSchemaCounts.get('tender_task_plan') ?? 0, plannerCallsAfterInterrupt, 'Resume reuses the source-validated saved task plan');
  assert.equal(providerSchemaCounts.get('technical_section_route') ?? 0, routeCallsAfterInterrupt, 'Resume reuses the completed routing artifact instead of repeating the model call');
  assert.ok(resumed.analysis.requirements.some(row => row.quote === quotes[0]));
  scenario='planner-exclusion-conflict';
  const reopenedByRouter=await analyze(short);
  assert.equal(reopenedByRouter.ok,true,reopenedByRouter.error);
  assert.ok(reopenedByRouter.analysis.requirements.some(row=>row.quote===quotes[0]),'The page-local router can restore a task-planner exclusion when its source-grounded decision disagrees');
  assert.equal(reopenedByRouter.analysis.coverage.pages[0].routingDisposition,'uncertain','A planner/router disagreement keeps the page in review instead of silently excluding it');
  scenario='slow-general-extraction';
  const slowGeneral=await analyze(short);
  assert.equal(slowGeneral.ok,true,slowGeneral.error);
  const slowExtractionProgress=progressObservations.filter(event=>event.scenario===scenario&&event.stage==='extracting').map(event=>event.message);
  const requestProgressIndex=slowExtractionProgress.findIndex(message=>message==='Requesting technical extraction batches 1–1 of 1');
  const completedProgressIndex=slowExtractionProgress.findIndex(message=>message==='Received and parsed 1 of 1 technical extraction batches');
  assert.ok(requestProgressIndex>=0&&completedProgressIndex>requestProgressIndex,`Extraction progress reports the active request before reporting its parsed completion: ${JSON.stringify(slowExtractionProgress)}`);
  scenario='all-general-batches-fail';
  const noCompletedBatch=await analyze(short);
  assert.equal(noCompletedBatch.ok,false,'A response sheet is not produced when no extraction batch or other source-grounded stage completed');
  assert.equal('analysis' in noCompletedBatch,false,'An all-failed run does not emit an empty or partial response sheet');
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
  assert.equal(maximumGeneralExtractionConcurrency,4,'All four independent general extraction batches run concurrently under the process-wide limit of six');
  assert.deepEqual(batched.analysis.requirements.map(row=>row.quote),quotes,'Concurrent extraction preserves deterministic source order and all grounded fixture requirements');
  const batchedProgress=progressObservations.filter(event=>event.scenario===scenario&&event.stage==='extracting').map(event=>event.message);
  assert.ok(batchedProgress.includes('Received and parsed 4 of 4 technical extraction batches'));
  const batchThreeCompletedAt=generalExtractionBatchEvents.find(event=>event.firstPage===7&&event.event==='completed')?.at;
  const batchFourStartedAt=generalExtractionBatchEvents.find(event=>event.firstPage===10&&event.event==='started')?.at;
  assert.ok(Number.isFinite(batchThreeCompletedAt)&&Number.isFinite(batchFourStartedAt)&&batchFourStartedAt<batchThreeCompletedAt,'The fourth extraction batch starts when the first of the three active requests finishes, before the slow third request completes');
  scenario='resume-general-extraction';
  let interruptedExtractionRunId=null;
  const interruptedExtractionFingerprint=createHash('sha256').update(Buffer.from(multiPage.output('arraybuffer'))).digest('hex');
  const extractionCallsBeforeInterrupt=extractionCalls;
  const resumeRequestsBeforeInterrupt=resumeGeneralRequestStarts;
  await assert.rejects(analyze(multiPage, {
    stopAt: progress => progress.message === 'Received and parsed 1 of 4 technical extraction batches',
    onProgress: progress => { if (progress.resumable && progress.runId) interruptedExtractionRunId=progress.runId; },
  }), /scripted interruption|cancelled|aborted/i);
  assert.match(interruptedExtractionRunId ?? '', /^run_[a-f0-9]{32}$/i, 'The run handle is exposed after the first extraction unit has been checkpointed');
  assert.equal(resumeGeneralRequestStarts-resumeRequestsBeforeInterrupt,4,'All four bounded extraction requests reached the scripted provider before interruption');
  await restartApp();
  const resumedGeneral=await analyze(multiPage,{resumeRunId:interruptedExtractionRunId});
  assert.equal(resumedGeneral.ok,true,resumedGeneral.error);
  assert.deepEqual(resumedGeneral.analysis.requirements.map(row=>row.quote),quotes,'Resumed general extraction rehydrates the completed first batch and returns source-grounded rows');
  assert.equal(resumeGeneralRequestStarts-resumeRequestsBeforeInterrupt,7,'Resume reuses the completed extraction artifact and dispatches only the three unfinished batches');
  assert.ok(extractionCalls>extractionCallsBeforeInterrupt,'The resumed extraction executes the unfinished batches after the process restart');
  const modelCallsBeforeMismatch=providerRequestCount;
  const wrongSourceResume=await analyze(short,{resumeRunId:interruptedExtractionRunId});
  assert.equal(wrongSourceResume.ok,false,'A saved run cannot be resumed with another PDF');
  assert.match(wrongSourceResume.error,/does not match the saved analysis run/);
  const originalEndpoint=appOptions.env.OPENAI_BASE_URL;
  appOptions.env.OPENAI_BASE_URL=`${originalEndpoint}/different-config`;
  await restartApp();
  const wrongConfigResume=await analyze(multiPage,{resumeRunId:interruptedExtractionRunId});
  assert.equal(wrongConfigResume.ok,false,'A saved run cannot be resumed with a different model configuration');
  assert.match(wrongConfigResume.error,/different model or pipeline version/);
  assert.equal(providerRequestCount,modelCallsBeforeMismatch,'Source and configuration mismatches are rejected before any model call');
  appOptions.env.OPENAI_BASE_URL=originalEndpoint;
  await restartApp();
  scenario='partial-general-batch';
  const partialBatchPdf=new jsPDF();
  for(let page=1;page<=12;page++) {
    if(page>1)partialBatchPdf.addPage();
    partialBatchPdf.setFontSize(8);
    partialBatchPdf.text([quotes[page-1]??`Technical equipment page ${page} contains a specified test procedure.`,...Array.from({length:60},(_,line)=>`Technical context ${page}-${line} describes the equipment and its operating conditions.`)],20,30,{lineHeightFactor:1});
  }
  const partialBatch=await analyze(partialBatchPdf);
  assert.equal(partialBatch.ok,true,partialBatch.error);
  assert.deepEqual(partialBatch.analysis.requirements.map(row=>row.quote),quotes,'Successful extraction batches retain their grounded requirements in source order when another batch loses its provider connection');
  const incompleteBatchPages=partialBatch.analysis.coverage.pages.filter(page=>page.extractionStatus==='incomplete').map(page=>page.page);
  assert.deepEqual(incompleteBatchPages,[10,11,12],'Every page in the failed extraction batch stays explicitly incomplete');
  assert.ok(partialBatch.analysis.coverage.pages.filter(page=>page.page<=9).every(page=>page.extractionStatus==='complete'),'Successfully completed pages remain distinct from the incomplete batch');
  assert.match(partialBatch.analysis.reviewNote,/model-based extraction or page coverage calls could not complete/,'The partial response warns reviewers that coverage is incomplete');
  scenario='partial-general-batch-six-of-six';
  const sixBatchPdf=new jsPDF();
  for(let page=1;page<=18;page++) {
    if(page>1)sixBatchPdf.addPage();
    sixBatchPdf.setFontSize(8);
    const pageQuote=quotes[page-1]??`Technical equipment page ${page} contains a specified test procedure.`;
    sixBatchPdf.text([pageQuote,...Array.from({length:60},(_,line)=>`Technical context ${page}-${line} describes the equipment and its operating conditions.`)],20,30,{lineHeightFactor:1});
  }
  const sixBatchCallsBefore=extractionCalls;
  const sixBatchLogStart=logs.length;
  const sixBatchPartial=await analyze(sixBatchPdf);
  assert.equal(sixBatchPartial.ok,true,sixBatchPartial.error);
  assert.equal(extractionCalls-sixBatchCallsBefore,6,'The regression runs five extraction requests to completion before the sixth provider connection is dropped');
  assert.deepEqual(sixBatchPartial.analysis.requirements.map(row=>row.quote),quotes,'The five completed batches retain their source-grounded requirements after a final-batch connection failure');
  assert.deepEqual(sixBatchPartial.analysis.coverage.pages.filter(page=>page.extractionStatus==='incomplete').map(page=>page.page),[16,17,18],'Only pages in the failed sixth batch remain explicitly incomplete');
  assert.equal(sixBatchPartial.resumable,true,'A partial draft with retryable work is returned as resumable instead of being finalized');
  const sixBatchRunId=progressObservations.filter(event=>event.scenario===scenario&&event.runId).at(-1)?.runId;
  assert.match(sixBatchRunId??'',/^run_[a-f0-9]{32}$/,'The partial draft retains its opaque run handle');
  const sixBatchMessages=progressObservations.filter(event=>event.scenario===scenario&&event.stage==='extracting').map(event=>event.message);
  assert.ok(sixBatchMessages.includes('Received and parsed 5 of 6 technical extraction batches'),'The failing six-batch run reports all five completed batches before terminating with a partial result');
  assert.match(sixBatchPartial.analysis.reviewNote,/model-based extraction or page coverage calls could not complete/,'The five-of-six partial result keeps the existing incomplete-coverage warning');
  const sixBatchTiming=logs.slice(sixBatchLogStart).split('\n').filter(line=>line.startsWith('[TCE_MODEL_TIMING] ')).map(line=>JSON.parse(line.slice('[TCE_MODEL_TIMING] '.length))).filter(event=>event.requestKind==='general_requirement_extraction');
  assert.equal(sixBatchTiming.filter(event=>event.phase==='response_validated').length,5,'Timing distinguishes the five schema-valid responses from the dropped sixth request');
  assert.ok(sixBatchTiming.some(event=>event.phase==='request_failed'&&event.batchIndex===6&&event.failureKind==='provider_connection'),'The failed final batch is attributed to a provider connection error without logging tender or response content');
  const sixBatchCallsAfterFailure=extractionCalls;
  await restartApp();
  const sixBatchResumed=await analyze(sixBatchPdf,{resumeRunId:sixBatchRunId});
  assert.equal(sixBatchResumed.ok,true,sixBatchResumed.error);
  assert.equal(sixBatchResumed.resumable,false,'A run becomes terminal only after retryable extraction work completes');
  assert.equal(extractionCalls-sixBatchCallsAfterFailure,1,'Restarted partial analysis reruns only the failed sixth batch');
  assert.deepEqual(sixBatchResumed.analysis.requirements.map(row=>row.quote),quotes,'Resumption reuses five completed source artifacts and returns the complete source-ordered result');
  assert.ok(sixBatchResumed.analysis.coverage.pages.every(page=>page.extractionStatus==='complete'),'The retried pages become complete after successful recovery');
  scenario='invalid-extraction-shape';
  const invalidShapeLogStart=logs.length;
  const invalidShape=await analyze(short);
  assert.equal(invalidShape.ok,false,'A parseable JSON object without a requirements array is rejected');
  const invalidShapeTiming=logs.slice(invalidShapeLogStart).split('\n').filter(line=>line.startsWith('[TCE_MODEL_TIMING] ')).map(line=>JSON.parse(line.slice('[TCE_MODEL_TIMING] '.length))).filter(event=>event.requestKind==='general_requirement_extraction');
  assert.ok(invalidShapeTiming.some(event=>event.phase==='request_failed'&&event.failureKind==='other'),'A JSON parse success that fails the extraction shape is recorded as a failed request');
  assert.equal(invalidShapeTiming.some(event=>event.phase==='response_validated'),false,'A schema-invalid result is never logged as validated');
  scenario='route-batch-concurrency';
  const routingPdf=new jsPDF();
  for(let page=1;page<=30;page++) {
    if(page>1)routingPdf.addPage();
    routingPdf.setFontSize(8);
    routingPdf.text([quotes[(page-1)%quotes.length],...Array.from({length:20},(_,line)=>`Routing context ${page}-${line} describes a technical apparatus and its operating conditions.`)],20,30,{lineHeightFactor:1});
  }
  const concurrentRouting=await analyze(routingPdf);
  assert.equal(concurrentRouting.ok,true,concurrentRouting.error);
  assert.ok(maximumRoutingConcurrency>=2,'Independent page routing groups run concurrently within the analysis request limit');
  const firstRouteCompletedAt=routingBatchEvents.find(event=>event.group===1&&event.event==='completed')?.at;
  const secondRouteCompletedAt=routingBatchEvents.find(event=>event.group===2&&event.event==='completed')?.at;
  assert.ok(Number.isFinite(firstRouteCompletedAt)&&Number.isFinite(secondRouteCompletedAt)&&secondRouteCompletedAt<firstRouteCompletedAt,'A faster later routing group completes first while results remain merged in source order');
  assert.deepEqual(concurrentRouting.analysis.coverage.pages.map(page=>page.page),Array.from({length:30},(_,index)=>index+1),'Concurrent routing retains every page in deterministic source order');
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
  if (await isTesseractAvailable() && await isPopplerAvailable()) {
    const scanCanvas = createCanvas(1200, 1700);
    const scanContext = scanCanvas.getContext('2d');
    scanContext.fillStyle = '#ffffff';
    scanContext.fillRect(0, 0, 1200, 1700);
    scanContext.fillStyle = '#111111';
    scanContext.font = 'bold 46px Arial';
    scanContext.fillText('Pressure shall remain below 2 Pa.', 80, 850);
    const scannedPdf = new jsPDF({ unit: 'pt', format: 'a4' });
    scannedPdf.addImage(`data:image/jpeg;base64,${scanCanvas.toBuffer('image/jpeg', 72).toString('base64')}`, 'JPEG', 0, 0, 595, 842);
    assert.ok(scannedPdf.output('arraybuffer').byteLength < 1024 * 1024, 'Synthetic OCR input stays under the scripted upload limit');
    scenario = 'planner-ocr-resume';
    const plannerCallsBeforeOcrRun = providerSchemaCounts.get('tender_task_plan') ?? 0;
    let plannerOcrRunId = null;
    const interruptedPlannerOcr = await analyze(scannedPdf, { onProgress: progress => { if (progress.resumable && progress.runId) plannerOcrRunId = progress.runId; } });
    assert.equal(interruptedPlannerOcr.ok, false, 'A failed provider call leaves planner-selected OCR work unfinished');
    assert.match(plannerOcrRunId ?? '', /^run_[a-f0-9]{32}$/i, 'The failed OCR action retains its opaque resumable run handle');
    await restartApp();
    const plannerOcrResult = await analyze(scannedPdf, { resumeRunId: plannerOcrRunId });
    assert.equal(plannerOcrResult.ok, true, `${plannerOcrResult.error}: ${JSON.stringify(plannerOcrResult).slice(0, 2200)}`);
    assert.equal(failPlannerOcrOnce, false, 'The scripted provider interruption was reached and consumed');
    assert.equal(providerSchemaCounts.get('tender_task_plan') ?? 0, plannerCallsBeforeOcrRun + 2, 'OCR resume reuses the first plan, then requests a bounded decision after OCR succeeds');
    assert.equal(plannerOcrExtractionAttempts, 2, 'The failed OCR call is retried exactly once');
    assert.equal(plannerOcrRequestInputs.length, 1, 'The selected OCR operation produces one successful extraction response after retry');
    assert.ok(plannerOcrRequestInputs.every(text => /Pressure shall remain below 2 Pa\./i.test(text)), 'The successful retry sends only the selected OCR transcript as extraction input');
    const selectedOcr = plannerOcrResult.analysis.coverage.plannedInspections.find(item => item.mode === 'ocr');
    assert.ok(selectedOcr?.sourceId.includes(':ocr:'), 'The planner selects an OCR region ID from the parser inventory');
    assert.equal(selectedOcr.state, 'executed', 'The OCR action is executed only after its region transcript yields a grounded quote');
    const selectedOcrRequirement = plannerOcrResult.analysis.requirements.find(row => /pressure shall remain below 2 pa/i.test(row.quote));
    assert.ok(selectedOcrRequirement, 'The selected OCR transcript produces a source-verified review row');
    assert.ok(selectedOcrRequirement.sourceReference.sourceElementIds.includes(selectedOcr.sourceId), 'The requirement citation names the selected parser OCR region');
    assert.equal(selectedOcrRequirement.sourceReference.extractionMethod, 'tesseract-ocr');
    assert.equal(selectedOcrRequirement.reviewed, false, 'OCR-derived output remains unreviewed for visual confirmation');
  } else {
    console.log('Skipped planner OCR integration scenario: Poppler and Tesseract with English language data are required.');
  }
  const visualCanvas = createCanvas(1200, 600);
  const visualContext = visualCanvas.getContext('2d');
  visualContext.fillStyle = '#ffffff';
  visualContext.fillRect(0, 0, 1200, 600);
  visualContext.fillStyle = '#111111';
  visualContext.font = 'bold 54px Arial';
  visualContext.fillText('Pressure shall remain below 2 Pa.', 70, 320);
  const imageOnlyPdf = new jsPDF({ unit: 'pt', format: 'a4' });
  imageOnlyPdf.addImage(`data:image/jpeg;base64,${visualCanvas.toBuffer('image/jpeg', 88).toString('base64')}`, 'JPEG', 55, 180, 485, 245);
  scenario = 'planner-visual-region';
  const plannerCallsBeforeVisualRun = providerSchemaCounts.get('tender_task_plan') ?? 0;
  let plannerVisualRunId = null;
  const interruptedPlannerVisual = await analyze(imageOnlyPdf, { onProgress: progress => { if (progress.resumable && progress.runId) plannerVisualRunId = progress.runId; } });
  assert.equal(interruptedPlannerVisual.ok, false, 'A failed selected visual operation remains incomplete and resumable');
  assert.match(plannerVisualRunId ?? '', /^run_[a-f0-9]{32}$/i, 'The failed visual crop operation retains its opaque run handle');
  await restartApp();
  const plannerVisualResult = await analyze(imageOnlyPdf, { resumeRunId: plannerVisualRunId });
  assert.equal(plannerVisualResult.ok, true, `${plannerVisualResult.error}: ${JSON.stringify(plannerVisualResult).slice(0, 2200)}`);
  assert.equal(plannerVisualResult.resumable, false, 'The visual run completes after the selected crop is retried');
  assert.equal(failPlannerVisualOnce, false, 'The scripted visual provider interruption was reached');
  assert.equal(plannerVisualExtractionAttempts, 2, 'The selected visual region is retried exactly once');
  assert.equal(providerSchemaCounts.get('tender_task_plan') ?? 0, plannerCallsBeforeVisualRun + 2, 'Restart reuses the first visual plan, then requests a bounded decision after crop inspection');
  assert.equal(plannerVisualRequestInputs.length, 2, 'Both the interrupted call and its retry send a visual request');
  assert.ok(plannerVisualRequestInputs.every(item => item.imageCount === 1), 'Each planned visual call sends exactly one image');
  assert.ok(plannerVisualRequestInputs.every(item => !/Pressure shall remain below 2 Pa\./i.test(item.text)), 'The visual request contains no hidden full-page text transcript of the crop');
  assert.ok(plannerVisualRequestInputs.every(item => item.sizes[0].width < 1450 && item.sizes[0].height < 1000), 'The VLM receives the selected parser region crop, smaller than the rendered full page');
  const selectedVisual = plannerVisualResult.analysis.coverage.plannedInspections.find(item => item.mode === 'visual');
  assert.ok(selectedVisual?.sourceId.includes(':image:'), 'The plan selects a parser-owned image-region ID');
  assert.equal(selectedVisual.state, 'executed', 'Coverage reports the visual operation only after a successful crop inspection');
  const selectedVisualRequirement = plannerVisualResult.analysis.requirements.find(row => row.quote === 'Pressure shall remain below 2 Pa.'
    && row.sourceReference.sourceElementIds.includes(selectedVisual.sourceId));
  assert.ok(selectedVisualRequirement, `The model transcription remains available for human review: ${JSON.stringify({ requirements: plannerVisualResult.analysis.requirements.map(row => ({ quote: row.quote, sourceElementIds: row.sourceReference.sourceElementIds, extractionMethod: row.sourceReference.extractionMethod })), rejected: plannerVisualResult.analysis.rejectedSuggestionDetails, coverage: selectedVisual })}`);
  assert.deepEqual(selectedVisualRequirement.sourceReference.sourceElementIds, [selectedVisual.sourceId], 'The citation names only the selected parser image region');
  assert.equal(selectedVisualRequirement.sourceReference.extractionMethod, 'visual-transcription');
  assert.equal(selectedVisualRequirement.sourceReference.sourceText, '', 'VLM transcription is not presented as selectable source text');
  assert.equal(selectedVisualRequirement.sourceReference.transcribedText, selectedVisualRequirement.quote);
  assert.equal(selectedVisualRequirement.sourceReference.locationPrecision, 'approximate');
  assert.equal(selectedVisualRequirement.sourceReference.ocrConfidence, undefined, 'VLM output receives no fabricated OCR confidence');
  assert.equal(selectedVisualRequirement.reviewed, false, 'Visual transcription remains unreviewed');
  assert.equal(selectedVisualRequirement.ocrWarning, true, 'Visual transcription carries an explicit review warning');
  scenario='planner-table-resume';
  const planCallsBeforeTableRun=providerSchemaCounts.get('tender_task_plan')??0;
  let plannerTableRunId = null;
  const interruptedPlannerTable=await analyze(single,{onProgress:progress=>{if(progress.resumable&&progress.runId)plannerTableRunId=progress.runId;}});
  assert.equal(plannerTableClassificationCalls,1,'The planner-selected parser table reaches its row-classification handler');
  assert.equal(interruptedPlannerTable.ok,true,interruptedPlannerTable.error);
  assert.equal(interruptedPlannerTable.resumable,true,'A provider-failed planner table operation remains resumable');
  assert.ok(interruptedPlannerTable.analysis.coverage.plannedInspections.some(item=>item.mode==='table'&&item.state==='retryable'),'A failed planner table operation stays explicitly retryable');
  assert.match(plannerTableRunId??'',/^run_[a-f0-9]{32}$/,'The interrupted table analysis retains its opaque run handle');
  await restartApp();
  const resumedPlannerTable=await analyze(single,{resumeRunId:plannerTableRunId});
  assert.equal(resumedPlannerTable.ok,true,resumedPlannerTable.error);
  assert.equal(resumedPlannerTable.resumable,false,'The table run is complete after its selected handler succeeds');
  assert.equal(plannerTableClassificationCalls,2,'Restart retries the selected table classification exactly once');
  assert.equal(providerSchemaCounts.get('tender_task_plan')??0,planCallsBeforeTableRun+1,'Restart reuses the saved source-validated table plan');
  assert.ok(resumedPlannerTable.analysis.coverage.plannedInspections.some(item=>item.mode==='table'&&item.state==='executed'),'The parser-owned table operation is marked executed only after its handler succeeds');
  assert.ok(resumedPlannerTable.analysis.requirements.every(row=>row.sourceReference.sourceCell),'Planner table results retain exact table-cell citations');
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
  assert.deepEqual([...vectorAuditPageOrder].sort((left,right)=>left-right),[1,2,3],'Independent source-row audits retain every classified page');
  assert.deepEqual(vectorPagesResult.analysis.requirements.map(row=>row.page),[1,1,1,2,2,2,2,2,3,3,3],'Returned requirements preserve source page order');
  assert.equal(vectorPagesResult.analysis.requirements.find(row=>row.page===2)?.quote,'Maximum load on unit 2 shall be 10 kN.','A headerless continuation retains its inherited specification column');
  assert.equal(vectorPagesResult.analysis.requirements.find(row=>row.page===2)?.sourceColumnMap?.[0]?.header,'Technical Parameters NIQ','A headerless continuation inherits the prior verified page map');
  assert.equal(vectorPagesResult.analysis.requirements.find(row=>row.page===3)?.sourceColumnMap?.[2]?.header,'Specification');
  assert.ok(vectorPagesResult.analysis.requirements.every(row=>row.sourceReference.sourceCell),'Parallel inspection preserves source-row citations');
  scenario='vector-page-straggler';
  vectorLabelEvents.length=0;vectorLabelRequestCount=0;maximumVectorLabelConcurrency=0;vectorAuditPageOrder.length=0;
  const stragglerPdf=new jsPDF({unit:'pt'});stragglerPdf.setFontSize(8);
  for(let page=1;page<=17;page++){
    if(page>1)stragglerPdf.addPage();
    stragglerPdf.text('TECHNICAL SPECIFICATION',40,40);
    const rows=page===1
      ? [['Technical Parameters NIQ','Remark'],['Maximum load on unit 1 shall be 10 kN.',''],['Operating temperature shall be -10 to 50 °C.','']]
      : page===2
        ? [['Maximum load on unit 2 shall be 10 kN.',''],['Supply voltage shall be 230 V AC.',''],['Operating temperature shall be -10 to 50 °C.',''],['Crosshead speed shall be 500 mm/min.',''],['Load accuracy shall be within 1%.','']]
        : [['S. No.','Parameter','Specification'],[String(page),'Load frame',`Maximum load on unit ${page} shall be 10 kN.`],['2','Power','Supply voltage shall be 230 V AC.'],['3','Temperature','Operating temperature shall be -10 to 50 °C.']];
    const widths=page===1||page===2?[370,130]:[55,140,305];
    rows.forEach((cells,row)=>{let x=40;cells.forEach((value,column)=>{const width=widths[column];stragglerPdf.rect(x,70+row*38,width,38);if(value)stragglerPdf.text(value,x+3,88+row*38);x+=width;});});
  }
  const stragglerResult=await analyze(stragglerPdf);
  assert.equal(stragglerResult.ok,true,stragglerResult.error);
  const firstClassificationComplete=vectorLabelEvents.find(event=>event.page===2&&event.event==='completed');
  const lastPageClassificationStart=vectorLabelEvents.find(event=>event.page===17&&event.event==='started');
  assert.ok(lastPageClassificationStart&&firstClassificationComplete&&lastPageClassificationStart.at<firstClassificationComplete.at,`A slow early page does not hold later independent table pages behind a wave barrier (${JSON.stringify({vectorLabelRequestCount,firstClassificationComplete,lastPageClassificationStart,firstEvents:vectorLabelEvents.slice(0,8),lastEvents:vectorLabelEvents.slice(-8)})})`);
  assert.equal(maximumVectorLabelConcurrency,6,'Large vector inspections use the process-wide bounded limit of six provider requests');
  const requirementPages=stragglerResult.analysis.requirements.map(row=>row.page);
  assert.deepEqual(requirementPages,[...requirementPages].sort((left,right)=>left-right),'Sliding scheduling still returns requirements in source order');
  assert.ok(vectorAuditPageOrder.length>0&&vectorAuditPageOrder.length<=16,'The deterministic semantic-audit cap remains in force');
  assert.deepEqual(vectorAuditPageOrder,[...vectorAuditPageOrder].sort((left,right)=>left-right),'The semantic-audit budget reserves pages in source order');
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
  assert.deepEqual(progressObservations.slice(tableProgressStart).filter(event=>event.message==='Reading table rows and auditing independent requirements').map(event=>[event.current,event.total]),[[0,2],[1,2],[2,2]],'Bounded mixed-layout vector processing reports each independently completed page');
  const textAuditProgress=progressObservations.slice(tableProgressStart).filter(event=>event.message==='Checking routed technical text for omitted requirements');
  assert.ok(textAuditProgress.some(event=>event.stage==='coverage'&&event.current===0&&event.total>0),'Text-page completeness audit announces its active stage before waiting for the model');
  assert.equal(mixed.analysis.normalizedTables,true);
  const ambiguousSourceRow = mixed.analysis.coverage.pages[0].sourceTableCoverageRows.find(row=>row.cells.some(cell=>cell.includes('Unclear source row')));
  assert.ok(ambiguousSourceRow);
  assert.equal(ambiguousSourceRow.sourceClassification,'ambiguous');
  assert.equal(ambiguousSourceRow.classificationReason,'ambiguous_source_structure');
  assert.equal(ambiguousSourceRow.disposition,'candidate','ambiguous source rows remain visible as review candidates without entering the response matrix');
  const auditedSourceRow = mixed.analysis.coverage.pages[0].sourceTableCoverageRows.find(row=>row.cells.some(cell=>cell.includes('Calibration report shall be supplied.')));
  assert.equal(auditedSourceRow?.semanticCoverageStatus,'possible_gap','possible semantic omission is surfaced on its detected source row');
  assert.match(auditedSourceRow?.semanticCoverageNote ?? '',/second independently assessable obligation/i);
  assert.equal(mixed.analysis.coverage.pages[0].sourceTableRowsNotShown,7,'audit states are retained for all rows even when the UI preview is capped');
  assert.deepEqual(ambiguousSourceRow.matchedRequirementIds,[],'Ambiguous source content stays out of output requirements and remains reviewable');
  assert.ok(mixed.analysis.classificationReviewCandidates.some(candidate=>candidate.page===1&&candidate.quote.includes('Source layout cannot be resolved')),'ambiguous source content is retained for explicit classification review');
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
  const generatedTraceFiles=(await readdir(forensicTraceDirectory)).filter(file=>!existingTraceFiles.has(file));
  assert.ok(generatedTraceFiles.length>0,'Opt-in synthetic pipeline runs write local forensic traces');
  const traces=await Promise.all(generatedTraceFiles.map(async file=>JSON.parse(await readFile(path.join(forensicTraceDirectory,file),'utf8'))));
  for(const trace of traces){
    const rows=trace.candidates;
    const counts=rows.reduce((total,row)=>{total[row.disposition]=(total[row.disposition]??0)+1;return total;},{accepted:0,rejected:0,duplicate:0,merged:0,discarded:0,incomplete:0});
    assert.equal(rows.length,trace.summary.total,'Every generated candidate is represented in the trace');
    assert.equal(counts.accepted+counts.rejected+counts.duplicate+counts.merged+counts.discarded+counts.incomplete,trace.summary.total,'Accepted, rejected, duplicate, merged, discarded, and incomplete records reconcile');
    if(trace.documentFingerprint===interruptedExtractionFingerprint&&counts.incomplete>0) {
      assert.ok(counts.incomplete>0,'Candidates from the deliberately interrupted run remain explicitly incomplete rather than silently accepted');
    } else {
      assert.equal(counts.incomplete,0,'Every non-interrupted scripted fixture candidate reaches a terminal disposition');
    }
    assert.equal(new Set(rows.map(row=>row.candidateId)).size,rows.length,'Candidate IDs remain unique within each run');
    assert.ok(rows.every(row=>row.documentFingerprint===trace.documentFingerprint));
  }
  assert.equal(traces.filter(trace=>trace.documentFingerprint===interruptedExtractionFingerprint&&trace.candidates.some(row=>row.disposition==='incomplete')).length,1,'The deliberate interruption produces exactly one trace with explicit incomplete candidates');
  const proseTrace=traces.find(trace=>trace.candidates.some(row=>row.modelQuote===recovery));
  assert.ok(proseTrace,'The deliberate omission-audit recovery has a trace record');
  const recoveredTrace=proseTrace.candidates.find(row=>row.modelQuote===recovery);
  assert.equal(recoveredTrace.origin,'text_page_omission_audit');
  assert.equal(recoveredTrace.disposition,'accepted');
  assert.ok(recoveredTrace.finalRequirementId);
  assert.equal(recoveredTrace.sourceQuote,recovery,'The parser source quote is retained separately from the model proposal');
  assert.ok(proseTrace.candidates.some(row=>row.origin==='initial_extraction'&&row.rejectionCategory==='source_quote_or_location_not_verified'),'The fixture preserves an initially generated claim rejected by source validation');
  const sourceRowRecoveryTrace=traces.find(trace=>trace.candidates.some(row=>row.origin==='source_row_recovery'&&row.modelQuote==='Calibration report shall be supplied.'));
  const sourceRowRecovery=sourceRowRecoveryTrace?.candidates.find(row=>row.origin==='source_row_recovery'&&row.modelQuote==='Calibration report shall be supplied.');
  assert.equal(sourceRowRecovery?.disposition,'accepted','Source-row recovery candidates are traced through acceptance');
  assert.ok(sourceRowRecovery.sourceRowId&&sourceRowRecovery.sourceCellId,'Source-row recovery retains parser row and cell identity');
  const visualAuditTrace=traces.find(trace=>trace.candidates.some(row=>row.origin==='visual_page_omission_audit'&&row.modelQuote==='The centrifuge shall accommodate 10 samples.'));
  const visualAuditDuplicate=visualAuditTrace?.candidates.find(row=>row.origin==='visual_page_omission_audit'&&row.modelQuote==='The centrifuge shall accommodate 10 samples.');
  assert.equal(visualAuditDuplicate?.disposition,'duplicate','A visually audited proposal already covered by extraction is traced as a duplicate');
  assert.ok(visualAuditDuplicate.relatedCandidateId,'Duplicate audit candidates link to the corresponding existing candidate');
  console.log(JSON.stringify({passed:true,cases:['fresh-process resume reuses the validated plan and completed routing artifact','planner-selected native text executes against its exact parser block and leaves other blocks to fallback','empty planner output stays uncovered and remains eligible for fallback','planner-selected native-text unit retries after process restart and reuses its saved plan','planner-selected OCR region is source-grounded, checkpointed and retried after process restart','planner-selected image crop stays image-cited when identical OCR text exists and retries after process restart','partial provider failure pauses the run and restart retries only the failed extraction batch','zero-candidate extraction reports incompleteness without implying no requirements exist','zero-accepted run retains rejected-only diagnostics without creating requirements','model cannot assert source location or bypass technical filtering','verified cross-section conflict routes both cited pages and displays both source quotes','unsupported cross-section quote is rejected and leaves its pages uncertain','mixed bold heading retains assessable body','single-content source table preserved','independent vector tables run concurrently while headerless continuations inherit verified maps and audits remain source-ordered','bounded mixed-layout vector processing reports completed waves','text-page completeness audit announces its active stage','failed batches preserve successful cited work and mark failed pages incomplete','five parsed batches plus sixth-batch provider connection failure return an explicitly incomplete partial result','parseable JSON with invalid extraction shape is recorded as failed, not validated','all failed extraction batches do not return a partial sheet','high-confidence visual completions remain unverified and out of exports','case-sensitive units retained','equal recovery quotes not duplicated','unsupported suggestions do not consume review capacity','verified response limit rejects without partial output','short unfamiliar clause','mixed schedule and prose','bounded five-page extraction','checker recovers deliberately omitted requirement','source validator rejects deliberately corrupted numeric value','vector-row semantic gap is surfaced without mutating extraction','invalid page rejection','exact source evidence','editable sheet with locked citations','different table schemas plus narrative page','16-row equipment grouping'],checkerMutationContract:{kind:'scripted provider contract, not a real-tender score',deliberatelyOmittedRequirements:1,omissionAuditRecovered:omissionAuditReturnedRecovery,recoveredQuoteGrounded:recoveredRequirement?.sourceReference.sourceText.replace(/\s+/g,' ').trim()===recovery,corruptedNumericClaims:1,corruptedClaimProposed:corruptedNumericClaimProposed,corruptedClaimRejected:rejectedCorruption?.reason==='source_quote_or_location_not_verified',originalNumericRequirementPreserved:analysis.requirements.some(row=>row.quote===quotes[1]),semanticGapSignalRecorded:auditedSourceRow?.semanticCoverageStatus==='possible_gap',realTenderQualityScore:null},routeCalls,extractionCalls}));
} finally {
  child.kill('SIGTERM');
  if(child.exitCode===null)await Promise.race([once(child,'exit'),new Promise(resolve=>setTimeout(resolve,3000))]);
  if(child.exitCode===null)child.kill('SIGKILL');
  const newTraceFiles=(await readdir(forensicTraceDirectory).catch(()=>[])).filter(file=>!existingTraceFiles.has(file));
  await Promise.all(newTraceFiles.map(file=>unlink(path.join(forensicTraceDirectory,file)).catch(()=>undefined)));
  provider.closeAllConnections();await new Promise(resolve=>provider.close(resolve));
  await rm(runStoreDirectory,{recursive:true,force:true});
}
