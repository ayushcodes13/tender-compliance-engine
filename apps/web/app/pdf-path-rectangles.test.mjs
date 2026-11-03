import test from "node:test";
import assert from "node:assert/strict";
import { extractPdfPathRectangles, hasTableGridGeometry } from "./pdf-path-rectangles.ts";

const operations = { rectangle: 4, moveTo: 13, lineTo: 14, closePath: 18 };

test("finds a closed four-corner table cell path", () => {
  assert.deepEqual(extractPdfPathRectangles(
    [13, 14, 14, 14, 18],
    [40, 60, 740, 60, 740, 100, 40, 100],
    operations,
  ), [{ x: 40, y: 60, width: 700, height: 40 }]);
});

test("finds separate cells encoded as subpaths and keeps rectangle operators", () => {
  assert.deepEqual(extractPdfPathRectangles(
    [13, 14, 14, 14, 18, 13, 14, 14, 14, 18, 4],
    [40, 60, 500, 60, 500, 100, 40, 100, 500, 60, 740, 60, 740, 100, 500, 100, 800, 60, 100, 40],
    operations,
  ), [
    { x: 40, y: 60, width: 460, height: 40 },
    { x: 500, y: 60, width: 240, height: 40 },
    { x: 800, y: 60, width: 100, height: 40 },
  ]);
});

test("ignores paths that are not closed rectangles or are too small", () => {
  assert.deepEqual(extractPdfPathRectangles(
    [13, 14, 14, 18, 13, 14, 14, 14, 18],
    [40, 60, 500, 60, 500, 100, 40, 60, 60, 60, 60, 64, 40, 64],
    operations,
  ), []);
});

test("recognizes a table from repeated long horizontal and vertical borders", () => {
  const borders = [
    ...[20, 40, 60, 80].map((y) => ({ x: 10, y, width: 180, height: 1 })),
    ...[10, 50, 100, 190].map((x) => ({ x, y: 20, width: 1, height: 60 })),
  ];
  assert.equal(hasTableGridGeometry(borders, 200, 100), true);
  assert.equal(hasTableGridGeometry(borders.slice(0, 5), 200, 100), false);
});

test('normalizes negative rectangle dimensions used by top-origin PDF generators',()=>{
  assert.deepEqual(extractPdfPathRectangles([4,4],[40,500,120,-30,200,500,-80,-30],operations),[
    {x:40,y:470,width:120,height:30},{x:120,y:470,width:80,height:30},
  ]);
});
