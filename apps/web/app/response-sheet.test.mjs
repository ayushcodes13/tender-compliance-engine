import test from "node:test";
import assert from "node:assert/strict";
import { buildResponseSheet, removeResponseSheetRow, updateResponseSheetCell, splitRequirementSubpoints } from "./response-sheet.ts";

const structured = {
  extractionMode: "structured-table",
  requirements: [{
    id: "req-1", text: "Universal Testing Machine", parameter: "Universal Testing Machine (300 kN)",
    quote: "High performance • auto ranging", specifications: ["High performance", "Auto ranging"], page: 17,
  }],
};

test("builds one editable response row per structured subpoint and preserves shared heading", () => {
  const sheet = buildResponseSheet(structured);
  assert.equal(sheet.rows.length, 2);
  assert.deepEqual(sheet.rows.map((row) => row.values[0]), ["Universal Testing Machine (300 kN)", "Universal Testing Machine (300 kN)"]);
  assert.deepEqual(sheet.rows.map((row) => row.values[1]), ["High performance", "Auto ranging"]);
  assert.deepEqual(sheet.rows.map((row) => row.values.at(-1)), ["Page 17", "Page 17"]);
});

test("edits one exported cell without changing its source identity or citation", () => {
  const sheet = buildResponseSheet(structured);
  const edited = updateResponseSheetCell(sheet, sheet.rows[1].id, 1, "Auto ranging force readout");
  assert.equal(edited.rows[1].values[1], "Auto ranging force readout");
  assert.equal(edited.rows[0].values[1], "High performance");
  assert.equal(edited.rows[1].sourceRequirementId, "req-1");
  assert.equal(edited.rows[1].values.at(-1), "Page 17");
});

test("editing a shared heading updates every row in that contiguous group", () => {
  const sheet = buildResponseSheet(structured);
  const edited = updateResponseSheetCell(sheet, sheet.rows[0].id, 0, "UTM 300 kN");
  assert.deepEqual(edited.rows.map((row) => row.values[0]), ["UTM 300 kN", "UTM 300 kN"]);
});

test("source page cells cannot be edited and removed rows leave the original sheet intact", () => {
  const sheet = buildResponseSheet(structured);
  const lastColumn = sheet.columns.length - 1;
  const unchanged = updateResponseSheetCell(sheet, sheet.rows[0].id, lastColumn, "Page 99");
  assert.equal(unchanged.rows[0].values[lastColumn], "Page 17");
  const reduced = removeResponseSheetRow(sheet, sheet.rows[0].id);
  assert.equal(reduced.rows.length, 1);
  assert.equal(sheet.rows.length, 2);
});

test("keeps source-defined columns and creates distinct IDs for split requirement rows", () => {
  const sheet = buildResponseSheet({
    sourceColumns: [
      { header: "Heading", role: "heading" },
      { header: "Technical Parameters", role: "specification" },
      { header: "Remarks", role: "remark" },
    ],
    requirements: [{ id: "req-2", text: "Product performance • accuracy", headingPrefix: "Product", quote: "Product performance • accuracy", page: 8 }],
  });
  assert.deepEqual(sheet.columns.map((column) => column.header), ["Heading", "Technical Parameters", "Remarks", "Compliance (Yes / No)", "Source page"]);
  assert.equal(sheet.rows.length, 2);
  assert.notEqual(sheet.rows[0].id, sheet.rows[1].id);
  assert.deepEqual(sheet.rows.map((row) => row.values[1]), ["performance", "• accuracy"]);
});

test("preserves every source column for an explicit multi-column compliance report", () => {
  const sheet = buildResponseSheet({
    sourceColumns: [
      { header: "S. No.", role: "serial" },
      { header: "Specification", role: "heading" },
      { header: "Description", role: "specification" },
      { header: "Comply (Yes/No)", role: "compliance" },
      { header: "Remarks/Justifications", role: "remark" },
    ],
    extractionMode: "visual-compliance-sheet",
    requirements: [
      { id: "req-1", text: "≥ 300 mm", quote: "≥ 300 mm", sourceCells: ["3", "Thickness", "≥ 300 mm", "", ""], page: 20 },
      { id: "req-2", text: "≥ 4 mm", quote: "≥ 4 mm", sourceCells: ["4", "Top skin thickness", "≥ 4 mm", "", ""], page: 20 },
    ],
  });
  assert.deepEqual(sheet.columns.map((column) => column.header), [
    "S. No.", "Specification", "Description", "Comply (Yes/No)", "Remarks/Justifications", "Source page",
  ]);
  assert.deepEqual(sheet.rows.map((row) => row.values), [
    ["3", "Thickness", "≥ 300 mm", "", "", "Page 20"],
    ["4", "Top skin thickness", "≥ 4 mm", "", "", "Page 20"],
  ]);
});

test("merges blank page continuations but keeps a numbered requirement on the next page separate", () => {
  const sheet = buildResponseSheet({
    sourceColumns: [
      { header: "S. No.", role: "serial" },
      { header: "Specification", role: "heading" },
      { header: "Description", role: "specification" },
    ],
    extractionMode: "visual-compliance-sheet",
    requirements: [
      { id: "req-3", text: "6 EA", quote: "6 EA", sourceCells: ["3", "Number of Isolators", "6 EA"], page: 23 },
      { id: "req-5", text: "1.5 Hz or lower", quote: "1.5 Hz or lower", sourceCells: ["5", "Vertical Isolation, Resonance", "1.5 Hz or lower"], page: 24, continuationOfPrevious: true },
      { id: "req-10", text: "The service requirement starts here.", quote: "The service requirement starts here.", sourceCells: ["10", "Service", "The service requirement starts here."], page: 25 },
      { id: "req-11", text: "warranty will be extended accordingly.", quote: "warranty will be extended accordingly.", sourceCells: ["", "", "warranty will be extended accordingly."], page: 26, continuationOfPrevious: true },
    ],
  });
  assert.equal(sheet.rows.length, 3);
  assert.deepEqual(sheet.rows.slice(0, 2).map((row) => row.values.slice(0, 3)), [
    ["3", "Number of Isolators", "6 EA"],
    ["5", "Vertical Isolation, Resonance", "1.5 Hz or lower"],
  ]);
  assert.deepEqual(sheet.rows[2].values.slice(0, 3), [
    "10", "Service", "The service requirement starts here. warranty will be extended accordingly.",
  ]);
  assert.equal(sheet.rows[2].values.at(-1), "Pages 25 and 26");
  assert.deepEqual(sheet.rows[2].sourceRequirementIds, ["req-10", "req-11"]);
});

test('normalizes different annexure layouts while keeping all 16 descriptions in their equipment group', () => {
  const firstMap = [{header:'S. No.',role:'serial'},{header:'Specification',role:'heading'},{header:'Description',role:'specification'}];
  const secondMap = [...firstMap,{header:'Comply (Yes/No)',role:'compliance'},{header:'Remarks',role:'remark'}];
  const requirements = [];
  for (const [annexure,page,map] of [['Annexure-I',20,firstMap],['Annexure-II',23,secondMap]]) {
    requirements.push({id:`heading-${page}`,text:'A. T-SHAPE Optical Table System',quote:'A. T-SHAPE Optical Table System',page,rowType:'section',sourceSectionTitle:annexure});
    for(let i=1;i<=16;i++) requirements.push({id:`${page}-${i}`,text:`≥ ${i} mm`,quote:`≥ ${i} mm`,page,rowType:'requirement',sourceSectionTitle:annexure,sourceColumnMap:map,sourceCells:[String(i),`Parameter ${i}`,`≥ ${i} mm`,'','']});
  }
  requirements.push({id:'b',text:'B. Vibration isolator set',quote:'B. Vibration isolator set',page:23,rowType:'section',sourceSectionTitle:'Annexure-II'});
  requirements.push({id:'self-centering',text:'Self-centering option for better positioning',quote:'Self-centering option for better positioning',page:24,rowType:'requirement',sourceSectionTitle:'Annexure-II',sourceColumnMap:secondMap,sourceCells:['16','Additional requirements','Self-centering option for better positioning','','']});
  const sheet=buildResponseSheet({normalizedTables:true,requirements});
  assert.equal(sheet.rows.length,33);
  assert.deepEqual(sheet.columns.map(c=>c.header),['Equipment / group','Annexure / section','Specification','Description','Comply (Yes/No)','Any deviation','Remarks / Justifications','Source page']);
  assert.equal(sheet.rows.filter(r=>r.values[1]==='Annexure-I'&&r.values[0]==='A. T-SHAPE Optical Table System').length,16);
  assert.equal(sheet.rows.filter(r=>r.values[1]==='Annexure-II'&&r.values[0]==='A. T-SHAPE Optical Table System').length,16);
  assert.equal(sheet.rows.at(-1).values[0],'B. Vibration isolator set');
  assert.equal(sheet.rows.at(-1).values[7],'Page 24');
  assert.ok(sheet.rows.every(r=>r.values[4]===''&&r.values[5]===''));
  assert.equal(sheet.rows[2].values[3],'≥ 3 mm');
  assert.equal(sheet.columns.some(c=>c.header==='S. No.'),false);
});

test('keeps source-cell obligations independently answerable and annexure heading edits separate', () => {
  const mapping=[{header:'Parameter',role:'heading'},{header:'Value',role:'specification'}];
  const source={normalizedTables:true,requirements:[
    {id:'h1',text:'A. Table',quote:'A. Table',page:20,rowType:'section',sourceSectionTitle:'Annexure I'},
    {id:'p1',text:'First.',quote:'First.',page:20,exportGroupId:'cell1',sourceColumnMap:mapping,sourceCells:['Holes','First.'],sourceSectionTitle:'Annexure I'},
    {id:'p2',text:'Second.',quote:'Second.',page:20,exportGroupId:'cell1',sourceColumnMap:mapping,sourceCells:['Holes','Second.'],sourceSectionTitle:'Annexure I'},
    {id:'h2',text:'A. Table',quote:'A. Table',page:23,rowType:'section',sourceSectionTitle:'Annexure II'},
    {id:'p3',text:'Third.',quote:'Third.',page:23,sourceColumnMap:mapping,sourceCells:['Holes','Third.'],sourceSectionTitle:'Annexure II'},
  ]};
  const sheet=buildResponseSheet(source);
  assert.equal(sheet.rows.length,3);
  assert.deepEqual(sheet.rows.slice(0,2).map(row=>row.values[3]),['First.','Second.']);
  assert.deepEqual(sheet.rows.slice(0,2).map(row=>row.sourceRequirementIds),[['p1'],['p2']]);
  assert.ok(sheet.rows.slice(0,2).every(row=>row.values.slice(4,7).every(value=>value==='')));
  const edited=updateResponseSheetCell(sheet,sheet.rows[0].id,0,'Edited table');
  assert.equal(edited.rows[0].values[0],'Edited table');
  assert.equal(edited.rows[1].values[0],'Edited table');
  assert.equal(edited.rows[2].values[0],'A. Table');
});

test('normalized continuation retains both citations and additional source columns', () => {
  const mapping=[{header:'No.',role:'serial'},{header:'Item',role:'heading'},{header:'Required',role:'specification'},{header:'Maximum',role:'specification'},{header:'Quantity',role:'quantity'}];
  const source={normalizedTables:true,requirements:[
    {id:'h',text:'Table',quote:'Table',page:25,rowType:'section',sourceSectionTitle:'Annexure II'},
    {id:'a',text:'First part',quote:'First part',page:25,sourceColumnMap:mapping,sourceCells:['1','Service','First part','90 days','2'],sourceSectionTitle:'Annexure II'},
    {id:'b',text:'continued.',quote:'continued.',page:26,continuationOfPrevious:true,sourceColumnMap:mapping,sourceCells:['','','continued.','',''],sourceSectionTitle:'Annexure II'},
  ]};
  const sheet=buildResponseSheet(source);
  assert.equal(sheet.rows.length,1);
  assert.match(sheet.rows[0].values[3],/Maximum: 90 days/);
  assert.match(sheet.rows[0].values[3],/Quantity: 2/);
  assert.match(sheet.rows[0].values[3],/continued\./);
  assert.equal(sheet.rows[0].values[7],'Pages 25 and 26');
  assert.deepEqual(sheet.rows[0].sourceRequirementIds,['a','b']);
});

test('many verified obligations from one source cell retain one citation and response row each',()=>{
 const mapping=[{header:'Parameter',role:'heading'},{header:'Description',role:'specification'}];
 const requirements=Array.from({length:300},(_,index)=>({
  id:`subpoint-${index}`,text:`Constraint ${index} mm.`,quote:`Constraint ${index} mm.`,page:4,
  exportGroupId:'source-cell-4-1',sourceColumnMap:mapping,sourceCells:['Instrument',`Constraint ${index} mm.`],
 }));
 const sheet=buildResponseSheet({normalizedTables:true,requirements});
 assert.equal(sheet.rows.length,300);
 assert.deepEqual(sheet.rows.map(row=>row.sourceRequirementId),requirements.map(row=>row.id));
 assert.deepEqual(sheet.rows.map(row=>row.sourceRequirementIds),requirements.map(row=>[row.id]));
 assert.deepEqual(sheet.rows.map(row=>row.values[3]),requirements.map(row=>row.quote));
 assert.ok(sheet.rows.every(row=>row.values[4]===''&&row.values[5]===''&&row.values[6]===''));
});

test('source response-column notes remain source context while every OEM response field starts blank',()=>{
 const mapping=[{header:'Required specification',role:'specification'},{header:'Remark',role:'remark'},{header:'Compliance',role:'compliance'}];
 const sheet=buildResponseSheet({normalizedTables:true,requirements:[{id:'r',page:2,text:'Dopant cell',quote:'Dopant cell',sourceColumnMap:mapping,sourceCells:['Dopant cell','1 EA','To be confirmed']} ]});
 assert.equal(sheet.rows[0].values[3],'Dopant cell\nRemark: 1 EA\nCompliance: To be confirmed');
 assert.deepEqual(sheet.rows[0].values.slice(4,7),['','','']);
});

test('a verified mixed-cell heading stays above an assessable body row with the original citation',()=>{
 const title='16. Source shutter assembly';const full=title+' The system shall withstand 300 N.';
 const source={normalizedTables:true,requirements:[{id:'mixed',page:26,text:full,quote:full,headingPrefix:title,nativeHeadingPrefix:title,rowType:'requirement',sourceColumnMap:[{header:'Technical Parameters',role:'specification'}],sourceCells:[full]}]};
 const before=structuredClone(source),sheet=buildResponseSheet(source);
 assert.equal(sheet.rows.length,1);assert.equal(sheet.rows[0].values[0],title);assert.equal(sheet.rows[0].values[3],'The system shall withstand 300 N.');
 assert.deepEqual(sheet.rows[0].sourceRequirementIds,['mixed']);assert.deepEqual(source,before);
});

test('an unverified inline model prefix does not change the group of following sibling requirements',()=>{
 const mapping=[{header:'Technical Parameters',role:'specification'}];
 const source={normalizedTables:true,requirements:[
  {id:'h',page:26,text:'15. MBE sources',quote:'15. MBE sources',rowType:'section'},
  {id:'f',page:26,text:'f) Dopant cells Carbon source.',quote:'f) Dopant cells Carbon source.',rowType:'requirement',headingPrefix:'f) Dopant cells',sourceColumnMap:mapping,sourceCells:['f) Dopant cells Carbon source.']},
  {id:'g',page:26,text:'g) All cells require cooling.',quote:'g) All cells require cooling.',rowType:'requirement',sourceColumnMap:mapping,sourceCells:['g) All cells require cooling.']},
 ]};
 const sheet=buildResponseSheet(source);assert.deepEqual(sheet.rows.map(row=>row.values[0]),['15. MBE sources','15. MBE sources']);assert.equal(sheet.rows[0].values[3],'f) Dopant cells Carbon source.');
});

test("creates multi-level hierarchy (Section/Unit and Subsystem/Parameter) and mandatory response columns", () => {
  const source = {
    requirements: [
      { id: "h1", text: "Microwave Unit", quote: "Microwave Unit", rowType: "section", page: 2 },
      { id: "s1", text: "Microwave Bridge", quote: "Microwave Bridge", rowType: "section", page: 2 },
      { id: "r1", text: "Working frequency range: 9.2 — 9.9 GHz;", quote: "Working frequency range: 9.2 — 9.9 GHz;", page: 2 },
      { id: "s2", text: "Microwave Power", quote: "Microwave Power", rowType: "section", page: 2 },
      { id: "r2", text: "Output microwave power: 200 mW", quote: "Output microwave power: 200 mW", page: 2 },
      { id: "h2", text: "Console", quote: "Console", rowType: "section", page: 3 },
      { id: "s3", text: "Magnetic Field Controller", quote: "Magnetic Field Controller", rowType: "section", page: 3 },
      { id: "r3", text: "Operating range: -1 to +14 kG", quote: "Operating range: -1 to +14 kG", page: 3 },
    ],
  };

  const sheet = buildResponseSheet(source);
  assert.deepEqual(
    sheet.columns.map((c) => c.header),
    [
      "Section / Unit",
      "Subsystem / Parameter",
      "Tender requirement",
      "Compliance (Yes / No)",
      "Remarks / Justifications",
      "Source page",
    ],
  );
  assert.equal(sheet.rows.length, 3);
  assert.equal(sheet.rows[0].values[0], "Microwave Unit");
  assert.equal(sheet.rows[0].values[1], "Microwave Bridge");
  assert.equal(sheet.rows[0].values[2], "Working frequency range: 9.2 — 9.9 GHz;");
  assert.equal(sheet.rows[0].values[3], "");
  assert.equal(sheet.rows[0].values[4], "");

  assert.equal(sheet.rows[1].values[0], "Microwave Unit");
  assert.equal(sheet.rows[1].values[1], "Microwave Power");
  assert.equal(sheet.rows[1].values[2], "Output microwave power: 200 mW");

  assert.equal(sheet.rows[2].values[0], "Console");
  assert.equal(sheet.rows[2].values[1], "Magnetic Field Controller");
  assert.equal(sheet.rows[2].values[2], "Operating range: -1 to +14 kG");
});

test("maintains individual subrows per requirement under the same subsystem with distinct compliance and remarks cells", () => {
  const source = {
    requirements: [
      { id: "h1", text: "EPR Software", quote: "EPR Software", rowType: "section", page: 3 },
      { id: "s1", text: "Workstation", quote: "Workstation", rowType: "section", page: 3 },
      { id: "p1", text: "OS: Linux;", quote: "OS: Linux;", page: 3 },
      { id: "p2", text: "Interfaces: USB, Ethernet;", quote: "Interfaces: USB, Ethernet;", page: 3 },
      { id: "p3", text: "DVD-R/W;", quote: "DVD-R/W;", page: 3 },
      { id: "p4", text: "TFT-Monitor;", quote: "TFT-Monitor;", page: 3 },
      { id: "s2", text: "Acquisition Controller", quote: "Acquisition Controller", rowType: "section", page: 3 },
      { id: "p5", text: "Controls all spectrometer devices;", quote: "Controls all spectrometer devices;", page: 3 },
    ],
  };

  const sheet = buildResponseSheet(source);
  // Each requirement forms its own subrow with its own compliance/remarks area
  assert.equal(sheet.rows.length, 5);
  assert.equal(sheet.rows[0].values[0], "EPR Software");
  assert.equal(sheet.rows[0].values[1], "Workstation");
  assert.equal(sheet.rows[0].values[2], "OS: Linux;");
  assert.deepEqual(sheet.rows[0].sourceRequirementIds, ["p1"]);

  assert.equal(sheet.rows[1].values[0], "EPR Software");
  assert.equal(sheet.rows[1].values[1], "Workstation");
  assert.equal(sheet.rows[1].values[2], "Interfaces: USB, Ethernet;");
  assert.deepEqual(sheet.rows[1].sourceRequirementIds, ["p2"]);

  assert.equal(sheet.rows[2].values[0], "EPR Software");
  assert.equal(sheet.rows[2].values[1], "Workstation");
  assert.equal(sheet.rows[2].values[2], "DVD-R/W;");
  assert.deepEqual(sheet.rows[2].sourceRequirementIds, ["p3"]);

  assert.equal(sheet.rows[3].values[0], "EPR Software");
  assert.equal(sheet.rows[3].values[1], "Workstation");
  assert.equal(sheet.rows[3].values[2], "TFT-Monitor;");
  assert.deepEqual(sheet.rows[3].sourceRequirementIds, ["p4"]);

  assert.equal(sheet.rows[4].values[0], "EPR Software");
  assert.equal(sheet.rows[4].values[1], "Acquisition Controller");
  assert.equal(sheet.rows[4].values[2], "Controls all spectrometer devices;");
  assert.deepEqual(sheet.rows[4].sourceRequirementIds, ["p5"]);
});

test("handles multi-level hierarchy when tender table has sourceColumns (Sl. No., Item Description, Compliance)", () => {
  const source = {
    sourceColumns: [
      { header: "Sl. No.", role: "serial" },
      { header: "Item Description", role: "specification" },
      { header: "Compliance (Yes/No)", role: "compliance" },
    ],
    requirements: [
      { id: "u1", text: "1. Microwave Unit", quote: "1. Microwave Unit", rowType: "section", page: 2 },
      { id: "s1", text: "Microwave Bridge", quote: "Microwave Bridge", rowType: "section", page: 2 },
      { id: "r1", text: "Working frequency range: 9.2 — 9.9 GHz;", quote: "Working frequency range: 9.2 — 9.9 GHz;", page: 2 },
      { id: "r2", text: "Frequency stability: +/- 10 kHz", quote: "Frequency stability: +/- 10 kHz", page: 2 },
      { id: "s2", text: "Microwave Power", quote: "Microwave Power", rowType: "section", page: 2 },
      { id: "r3", text: "Output microwave power: 200 mW", quote: "Output microwave power: 200 mW", page: 2 },
      { id: "u2", text: "2. Console", quote: "2. Console", rowType: "section", page: 3 },
      { id: "s3", text: "Workstation", quote: "Workstation", rowType: "section", page: 3 },
      { id: "r4", text: "Linux OS", quote: "Linux OS", page: 3 },
      { id: "r5", text: "DVD-R/W", quote: "DVD-R/W", page: 3 },
    ],
  };

  const sheet = buildResponseSheet(source);
  assert.deepEqual(
    sheet.columns.map((c) => c.header),
    [
      "Sl. No.",
      "Section / Unit",
      "Subsystem / Parameter",
      "Item Description",
      "Compliance (Yes / No)",
      "Remarks / Justifications",
      "Source page",
    ],
  );

  // 5 individual subrows across the subsystems
  assert.equal(sheet.rows.length, 5);

  // Row 0: Microwave Bridge - freq range
  assert.equal(sheet.rows[0].values[1], "Microwave Unit");
  assert.equal(sheet.rows[0].values[2], "Microwave Bridge");
  assert.equal(sheet.rows[0].values[3], "Working frequency range: 9.2 — 9.9 GHz;");
  assert.equal(sheet.rows[0].values[4], "");
  assert.equal(sheet.rows[0].values[5], "");
  assert.equal(sheet.rows[0].values[6], "Page 2");
  assert.deepEqual(sheet.rows[0].sourceRequirementIds, ["r1"]);

  // Row 1: Microwave Bridge - freq stability
  assert.equal(sheet.rows[1].values[1], "Microwave Unit");
  assert.equal(sheet.rows[1].values[2], "Microwave Bridge");
  assert.equal(sheet.rows[1].values[3], "Frequency stability: +/- 10 kHz");
  assert.equal(sheet.rows[1].values[4], "");
  assert.equal(sheet.rows[1].values[5], "");
  assert.equal(sheet.rows[1].values[6], "Page 2");
  assert.deepEqual(sheet.rows[1].sourceRequirementIds, ["r2"]);

  // Row 2: Microwave Power
  assert.equal(sheet.rows[2].values[1], "Microwave Unit");
  assert.equal(sheet.rows[2].values[2], "Microwave Power");
  assert.equal(sheet.rows[2].values[3], "Output microwave power: 200 mW");
  assert.equal(sheet.rows[2].values[4], "");
  assert.equal(sheet.rows[2].values[5], "");
  assert.deepEqual(sheet.rows[2].sourceRequirementIds, ["r3"]);

  // Row 3: Console -> Workstation - Linux
  assert.equal(sheet.rows[3].values[1], "Console");
  assert.equal(sheet.rows[3].values[2], "Workstation");
  assert.equal(sheet.rows[3].values[3], "Linux OS");
  assert.equal(sheet.rows[3].values[4], "");
  assert.equal(sheet.rows[3].values[5], "");
  assert.equal(sheet.rows[3].values[6], "Page 3");
  assert.deepEqual(sheet.rows[3].sourceRequirementIds, ["r4"]);

  // Row 4: Console -> Workstation - DVD
  assert.equal(sheet.rows[4].values[1], "Console");
  assert.equal(sheet.rows[4].values[2], "Workstation");
  assert.equal(sheet.rows[4].values[3], "DVD-R/W");
  assert.equal(sheet.rows[4].values[4], "");
  assert.equal(sheet.rows[4].values[5], "");
  assert.equal(sheet.rows[4].values[6], "Page 3");
  assert.deepEqual(sheet.rows[4].sourceRequirementIds, ["r5"]);
});

test("guarantees both Compliance and Remarks columns exist even when source table has only one", () => {
  // Source table with ONLY compliance column
  const sheetOnlyCompliance = buildResponseSheet({
    sourceColumns: [
      { header: "Specification", role: "specification" },
      { header: "Comply (Yes/No)", role: "compliance" },
    ],
    requirements: [
      { id: "r1", text: "Spec 1", quote: "Spec 1", page: 1, sourceCells: ["Spec 1", ""] },
    ],
  });
  const headers1 = sheetOnlyCompliance.columns.map((c) => c.header);
  assert.ok(headers1.some((h) => /compliance|comply/i.test(h)), "Contains compliance column");
  assert.ok(headers1.some((h) => /remark|justification/i.test(h)), "Contains added remarks column");

  // Source table with ONLY remark column
  const sheetOnlyRemark = buildResponseSheet({
    sourceColumns: [
      { header: "Specification", role: "specification" },
      { header: "Vendor Remarks", role: "remark" },
    ],
    requirements: [
      { id: "r2", text: "Spec 2", quote: "Spec 2", page: 1, sourceCells: ["Spec 2", ""] },
    ],
  });
  const headers2 = sheetOnlyRemark.columns.map((c) => c.header);
  assert.ok(headers2.some((h) => /compliance|comply/i.test(h)), "Contains added compliance column");
  assert.ok(headers2.some((h) => /remark|justification/i.test(h)), "Contains remarks column");
});

test("distinguishes physical PDF line wrapping from independent subclauses", () => {
  // Physical line wrap: should NOT be split into two separate requirements
  const wrapped = "The pump shall operate continuously at\nminimum pressure of 200 bar and 50 Hz.";
  const subpointsWrapped = splitRequirementSubpoints(wrapped);
  assert.equal(subpointsWrapped.length, 1);
  assert.equal(subpointsWrapped[0], "The pump shall operate continuously at minimum pressure of 200 bar and 50 Hz.");

  // Confirmed bullets / independent subclauses: SHOULD be split
  const bulleted = "• Operating range: -1 ... +14 kG;\n• Center field setting resolution: 18 bit (60 mG);";
  const subpointsBulleted = splitRequirementSubpoints(bulleted);
  assert.equal(subpointsBulleted.length, 2);
  assert.equal(subpointsBulleted[0], "• Operating range: -1 ... +14 kG;");
  assert.equal(subpointsBulleted[1], "• Center field setting resolution: 18 bit (60 mG);");

  // Numbered clauses: SHOULD be split
  const numbered = "1. Mainframe controller tower version\n2. Power supply and cabling";
  const subpointsNumbered = splitRequirementSubpoints(numbered);
  assert.equal(subpointsNumbered.length, 2);

  // Parameter ending with colon followed by bare value: should NOT be split into two rows
  const colonWrapped = "Minimum operating pressure:\n200 bar";
  const subpointsColon = splitRequirementSubpoints(colonWrapped);
  assert.equal(subpointsColon.length, 1);
  assert.equal(subpointsColon[0], "Minimum operating pressure: 200 bar");
});


