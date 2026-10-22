import assert from "node:assert/strict";
import test from "node:test";

import { extractVectorTableRows } from "./vector-table.ts";

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
    { quote: "a) Cracker source", cells: ["a) Cracker source", "1 no."], remark: "1 no.", rowHeight: 24, bbox: { x: 60, y: 680, width: 110, height: 12 }, remarkBox: { x: 450, y: 680, width: 30, height: 12 } },
    { quote: "b) Arsenic source", cells: ["b) Arsenic source", ""], rowHeight: 24, bbox: { x: 60, y: 704, width: 120, height: 12 } },
  ]);
});
