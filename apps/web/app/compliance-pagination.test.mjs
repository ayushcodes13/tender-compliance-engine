import test from "node:test";
import assert from "node:assert/strict";
import { attachLeadingContinuation, partitionRowsAtMarkers, splitRowBeforeLiteral } from "./compliance-pagination.ts";

test("splits a display row across a page break without losing or rewriting source text", () => {
  const source = "p) Blank substrate holder should also be included.";
  const rows = [{ text: "before" }, { text: source }, { text: "after" }];
  const split = splitRowBeforeLiteral(rows, "p) Blank substrate holder", "included.");

  assert.deepEqual(split?.map((row) => row.text), [
    "before",
    "p) Blank substrate holder should also be",
    "included.",
    "after",
  ]);
  assert.equal(split?.[1].text + " " + split?.[2].text, source);
  assert.equal(splitRowBeforeLiteral(rows, "missing", "included."), null);
});

test("finds page anchors across source line wraps", () => {
  const rows = [
    { text: "p) Molybdenum substrate holder compatible. Blank substrate holder should also be\nincluded." },
    { text: "The control system shall provide automatic long-term logging of all critical\nprocess parameters including temperatures." },
    { text: "final row" },
  ];
  const holder = splitRowBeforeLiteral(rows, "p) Molybdenum substrate holder", "included.");
  const logging = holder && splitRowBeforeLiteral(holder, "The control system shall provide automatic long-term logging", "process parameters including");
  const pages = logging && partitionRowsAtMarkers(logging, [
    "Blank substrate holder should also be",
    "The control system shall provide automatic long-term logging of all critical",
  ]);

  assert.deepEqual(pages?.map((page) => page.length), [1, 2, 2]);
  assert.equal(logging?.[0].text, "p) Molybdenum substrate holder compatible. Blank substrate holder should also be");
  assert.equal(logging?.[1].text, "included.");
  assert.equal(logging?.[2].text, "The control system shall provide automatic long-term logging of all critical");
  assert.equal(logging?.[3].text, "process parameters including temperatures.");
  const normalize = (text) => text.replace(/\s+/g, " ").trim();
  assert.equal(normalize(`${logging?.[0].text} ${logging?.[1].text}`), normalize(rows[0].text));
  assert.equal(normalize(`${logging?.[2].text} ${logging?.[3].text}`), normalize(rows[1].text));
});

test("partitions display rows at ordered page-boundary anchors", () => {
  const rows = ["p fragment", "p continuation", "page two end", "page three end", "final"]
    .map((text) => ({ text }));
  const pages = partitionRowsAtMarkers(rows, ["p fragment", "page two end", "page three end"]);

  assert.deepEqual(pages?.map((page) => page.map((row) => row.text)), [
    ["p fragment"],
    ["p continuation", "page two end"],
    ["page three end"],
    ["final"],
  ]);
  assert.equal(partitionRowsAtMarkers(rows, ["missing"]), null);
});

test("carries page-leading continuation text into the next row without losing the row", () => {
  const rows = [{ text: "continuation fragment" }, { text: "next requirement" }, { text: "following row" }];
  const displayRows = attachLeadingContinuation(rows);

  assert.deepEqual(displayRows?.map((row) => ({ text: row.text, pageContinuation: row.pageContinuation })), [
    { text: "next requirement", pageContinuation: "continuation fragment" },
    { text: "following row", pageContinuation: undefined },
  ]);
  assert.equal(attachLeadingContinuation([{ text: "single row" }]), null);
});
