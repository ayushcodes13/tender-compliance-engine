import assert from "node:assert/strict";
import test from "node:test";

import { extractVectorTableRows, isRepeatedTableHeader } from "./vector-table.ts";

test("extracts source text from paired vector table cells without joining adjacent rows", () => {
  const rectangles = [
    { x: 50, y: 100, width: 390, height: 24 }, { x: 441, y: 100, width: 70, height: 24 },
    { x: 50, y: 76, width: 390, height: 24 }, { x: 441, y: 76, width: 70, height: 24 },
    { x: 0, y: 0, width: 612, height: 792 },
  ];
  const items = [
    { str: "a)", x: 60, y: 116, box: { x: 60, y: 680, width: 12, height: 12 } },
    { str: "Cracker source", x: 80, y: 116, box: { x: 80, y: 680, width: 90, height: 12 } },
    { str: "1 no.", x: 450, y: 116, box: { x: 450, y: 680, width: 30, height: 12 } },
    { str: "b)", x: 60, y: 92, box: { x: 60, y: 704, width: 12, height: 12 } },
    { str: "Arsenic source", x: 80, y: 92, box: { x: 80, y: 704, width: 100, height: 12 } },
  ];
  assert.deepEqual(extractVectorTableRows(items, rectangles, 612, 792), [
    { quote: "a) Cracker source", cells: ["a) Cracker source", "1 no."], cellBoxes: [{ x: 60, y: 680, width: 110, height: 12 }, { x: 450, y: 680, width: 30, height: 12 }], remark: "1 no.", rowHeight: 24, bbox: { x: 60, y: 680, width: 110, height: 12 }, remarkBox: { x: 450, y: 680, width: 30, height: 12 } },
    { quote: "b) Arsenic source", cells: ["b) Arsenic source", ""], cellBoxes: [{ x: 60, y: 704, width: 120, height: 12 }, null], rowHeight: 24, bbox: { x: 60, y: 704, width: 120, height: 12 } },
  ]);
});

test("keeps every cell in a multi-column row instead of assuming the widest cell is the first column", () => {
  const rectangles = [
    { x: 40, y: 200, width: 55, height: 28 },
    { x: 95, y: 200, width: 95, height: 28 },
    { x: 190, y: 200, width: 205, height: 28 },
    { x: 395, y: 200, width: 90, height: 28 },
    { x: 40, y: 172, width: 55, height: 28 },
    { x: 95, y: 172, width: 95, height: 28 },
    { x: 190, y: 172, width: 205, height: 28 },
    { x: 395, y: 172, width: 90, height: 28 },
  ];
  const items = [
    { str: "1", x: 50, y: 216, box: { x: 50, y: 575, width: 8, height: 10 } },
    { str: "Thickness", x: 103, y: 216, box: { x: 103, y: 575, width: 52, height: 10 } },
    { str: "≥ 300 mm", x: 200, y: 216, box: { x: 200, y: 575, width: 65, height: 10 } },
    { str: "Yes", x: 405, y: 216, box: { x: 405, y: 575, width: 20, height: 10 } },
    { str: "2", x: 50, y: 188, box: { x: 50, y: 603, width: 8, height: 10 } },
    { str: "Top skin", x: 103, y: 188, box: { x: 103, y: 603, width: 52, height: 10 } },
    { str: "≥ 4 mm", x: 200, y: 188, box: { x: 200, y: 603, width: 48, height: 10 } },
    { str: "", x: 0, y: 0, box: null },
  ];
  const rows = extractVectorTableRows(items, rectangles, 612, 792);
  assert.deepEqual(rows.map((row) => row.cells), [
    ["1", "Thickness", "≥ 300 mm", "Yes"],
    ["2", "Top skin", "≥ 4 mm", ""],
  ]);
  assert.equal(rows[0].cellBoxes.length, 4);
});

test("recognizes repeated headers with two or more matching populated cells", () => {
  assert.equal(isRepeatedTableHeader(["S. No.", "Specification", "Description", "Comply"], ["Sr. No.", "Specification", "Description", "Comply"]), true);
  assert.equal(isRepeatedTableHeader(["1", "Thickness", "≥ 300 mm", ""], ["Sr. No.", "Specification", "Description", "Comply"]), false);
});

test("uses horizontal grid rules to keep wrapped table rows separate", () => {
  const rectangles = [];
  for (let row = 0; row < 5; row += 1) {
    const bottom = 100 + row * 20;
    rectangles.push(
      { x: 40, y: bottom, width: 40, height: 20 },
      { x: 80, y: bottom, width: 100, height: 20 },
      { x: 180, y: bottom, width: 220, height: 20 },
      { x: 40, y: bottom, width: 410, height: 0.5 },
    );
  }
  rectangles.push({ x: 40, y: 200, width: 410, height: 0.5 });
  const items = [];
  for (let row = 0; row < 5; row += 1) {
    const y = 110 + row * 20;
    items.push(
      { str: String(row + 1), x: 50, y, box: { x: 50, y: 640 - row * 20, width: 8, height: 10 } },
      { str: `Parameter ${row + 1}`, x: 90, y, box: { x: 90, y: 640 - row * 20, width: 60, height: 10 } },
      { str: `${row + 1} mm or better`, x: 190, y, box: { x: 190, y: 640 - row * 20, width: 80, height: 10 } },
    );
  }
  const rows = extractVectorTableRows(items, rectangles, 500, 700);
  assert.equal(rows.length, 5);
  assert.deepEqual(rows.map((row) => row.cells), [
    ["5", "Parameter 5", "5 mm or better"],
    ["4", "Parameter 4", "4 mm or better"],
    ["3", "Parameter 3", "3 mm or better"],
    ["2", "Parameter 2", "2 mm or better"],
    ["1", "Parameter 1", "1 mm or better"],
  ]);
});


test('header recognition does not erase unit case or numerical operators from data rows',()=>{
 assert.equal(isRepeatedTableHeader(['MW'],['mW']),false);
 assert.equal(isRepeatedTableHeader(['300 mm'],['≥ 300 mm']),false);
 assert.equal(isRepeatedTableHeader(['≥ 300 mm'],['≥ 300 mm']),true);
});

test('retains the font boundary inside a mixed heading and specification cell',()=>{
 const items=[
  {str:'16.',bold:true,x:45,y:190,box:{x:45,y:600,width:15,height:10}},
  {str:'Source shutter assembly',bold:true,x:70,y:190,box:{x:70,y:600,width:150,height:10}},
  {str:'The system shall withstand 300 N.',bold:false,x:45,y:170,box:{x:45,y:620,width:200,height:10}},
 ];
 const rows=extractVectorTableRows(items,[{x:40,y:150,width:300,height:60},{x:340,y:150,width:100,height:60}],600,800);
 assert.equal(rows[0].cellHeadingPrefixes[0],'16. Source shutter assembly');
 assert.equal(rows[0].cells[0],'16. Source shutter assembly The system shall withstand 300 N.');
});
