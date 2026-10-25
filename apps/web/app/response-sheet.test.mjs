import test from "node:test";
import assert from "node:assert/strict";
import { buildResponseSheet, removeResponseSheetRow, updateResponseSheetCell } from "./response-sheet.ts";

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
  assert.deepEqual(sheet.columns.map((column) => column.header), ["Heading", "Technical Parameters", "Remarks", "Source page"]);
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

test('reassembles source-cell subpoints and keeps separate annexure heading edits separate', () => {
  const mapping=[{header:'Parameter',role:'heading'},{header:'Value',role:'specification'}];
  const source={normalizedTables:true,requirements:[
    {id:'h1',text:'A. Table',quote:'A. Table',page:20,rowType:'section',sourceSectionTitle:'Annexure I'},
    {id:'p1',text:'First.',quote:'First.',page:20,exportGroupId:'cell1',sourceColumnMap:mapping,sourceCells:['Holes','First.'],sourceSectionTitle:'Annexure I'},
    {id:'p2',text:'Second.',quote:'Second.',page:20,exportGroupId:'cell1',sourceColumnMap:mapping,sourceCells:['Holes','Second.'],sourceSectionTitle:'Annexure I'},
    {id:'h2',text:'A. Table',quote:'A. Table',page:23,rowType:'section',sourceSectionTitle:'Annexure II'},
    {id:'p3',text:'Third.',quote:'Third.',page:23,sourceColumnMap:mapping,sourceCells:['Holes','Third.'],sourceSectionTitle:'Annexure II'},
  ]};
  const sheet=buildResponseSheet(source);
  assert.equal(sheet.rows.length,2);
  assert.equal(sheet.rows[0].values[3],'First. Second.');
  assert.deepEqual(sheet.rows[0].sourceRequirementIds,['p1','p2']);
  const edited=updateResponseSheetCell(sheet,sheet.rows[0].id,0,'Edited table');
  assert.equal(edited.rows[0].values[0],'Edited table');
  assert.equal(edited.rows[1].values[0],'A. Table');
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
