import test from "node:test";
import assert from "node:assert/strict";
import { discardContainedSuggestions, discardContainedSuggestionsByPage, keepParsedSourceCandidate, mergeVisualExportGroups, mergeVisualHeadingRows, mergeVisualRowContinuations, prepareVisualComplianceRows, sourceCandidateKey, splitSourceQuote } from "./visual-table.ts";

test("coverage recovery removes represented rows only from the same source page", () => {
  const draft = [{ page: 3, quote: "Range: 0 to 100 mm" }];
  const suggestions = [
    { page: 3, quote: "0 to 100 mm" },
    { page: 4, quote: "0 to 100 mm" },
    { page: 4, quote: "Probe travel: 25 mm" },
  ];

  assert.deepEqual(discardContainedSuggestionsByPage(draft, suggestions), [
    { page: 4, quote: "0 to 100 mm" },
    { page: 4, quote: "Probe travel: 25 mm" },
  ]);
});

test('coverage recovery does not duplicate an equal table quote or heading, but retains another page',()=>{
 const drafts=[{page:2,quote:'Range: 0 to 100 mm'},{page:2,quote:'A. Optical table'}];
 const otherPage={page:3,quote:'Range: 0 to 100 mm'};
 assert.deepEqual(discardContainedSuggestionsByPage(drafts,[
  {page:2,quote:'Range: 0 to 100 mm'},
  {page:2,quote:'Range:  0 to 100 mm'},
  {page:2,quote:'A. Optical table',row_type:'section'},otherPage,
 ]),[otherPage]);
});

test("keeps the compliance response rows in source order across source-page boundaries", () => {
  const rows = [
    { text: "page 8 row 1", page: 8 },
    { text: "page 8 row 2", page: 8 },
    { text: "page 9 row 1", page: 9 },
    { text: "page 10 row 1", page: 10 },
  ];
  assert.deepEqual(prepareVisualComplianceRows(rows), rows);
});

test("joins a heading row only when the visual model marks its adjacent descriptor", () => {
  const rows = [
    { text: "4. MBE sources", page: 9, rowType: "section", headingPrefix: "4. MBE sources", mergeWithNext: true },
    { text: "Vendor to provide flux isolation geometry.", page: 9, remark: "" },
    { text: "5. Source shutter assembly", page: 9, rowType: "section", mergeWithNext: false },
  ];
  assert.deepEqual(mergeVisualHeadingRows(rows), [
    { text: "4. MBE sources Vendor to provide flux isolation geometry.", page: 9, rowType: "section", headingPrefix: "4. MBE sources", mergeWithNext: false, remark: "" },
    { text: "5. Source shutter assembly", page: 9, rowType: "section", mergeWithNext: false },
  ]);
});

test("does not merge a lettered requirement even if visual metadata flags merge_with_next", () => {
  const rows = [
    { text: "c) Check layer uniformity.", page: 12, rowType: "requirement", mergeWithNext: true },
    { text: "d) Check Hall mobility.", page: 12, rowType: "requirement" },
    { text: "e) Show cracker efficiency.", page: 12, rowType: "requirement" },
  ];
  assert.deepEqual(mergeVisualHeadingRows(rows), rows);
});

test("reassembles AI-split items from the same source cell for DOCX export", () => {
  const rows = [
    { text: "c) Check uniformity.", page: 12, exportGroupId: "cell-12-4", sourceRowHeight: 48 },
    { text: "d) Check Hall mobility.", page: 12, exportGroupId: "cell-12-4", sourceRowHeight: 48 },
    { text: "e) Show cracker efficiency.", page: 12, exportGroupId: "cell-12-4", sourceRowHeight: 48 },
    { text: "f) Different source cell.", page: 12 },
  ];
  assert.deepEqual(mergeVisualExportGroups(rows), [
    { text: "c) Check uniformity.\nd) Check Hall mobility.\ne) Show cracker efficiency.", page: 12, exportGroupId: "cell-12-4", sourceRowHeight: 48 },
    { text: "f) Different source cell.", page: 12 },
  ]);
  assert.deepEqual(prepareVisualComplianceRows(rows).map((row) => row.text), [
    "c) Check uniformity.\nd) Check Hall mobility.\ne) Show cracker efficiency.",
    "f) Different source cell.",
  ]);
});

test("carries source row height when continuations or headings merge", () => {
  assert.equal(mergeVisualRowContinuations([
    { text: "first page", page: 8, sourceRowHeight: 24 },
    { text: "continued", page: 9, sourceRowHeight: 18, continuationOfPrevious: true },
  ])[0].sourceRowHeight, 42);
  assert.equal(mergeVisualHeadingRows([
    { text: "4. Sources", page: 8, rowType: "section", sourceRowHeight: 14, mergeWithNext: true },
    { text: "Supplier details", page: 8, sourceRowHeight: 23 },
  ])[0].sourceRowHeight, 37);
});

test("does not merge a visual heading decision across pages or through a populated remark cell", () => {
  assert.equal(mergeVisualHeadingRows([
    { text: "4. MBE sources", page: 9, rowType: "section", mergeWithNext: true },
    { text: "Vendor to provide flux isolation geometry.", page: 10 },
  ]).length, 2);
  assert.equal(mergeVisualHeadingRows([
    { text: "4. MBE sources", page: 9, rowType: "section", remark: "1 no.", mergeWithNext: true },
    { text: "Vendor to provide flux isolation geometry.", page: 9 },
  ]).length, 2);
});

test("joins an AI-identified page continuation into the prior export row", () => {
  const rows = [
    { text: "m) RHEED system description", page: 8, id: "first" },
    { text: "The analysis software shall be integrated.", page: 9, id: "continuation", continuationOfPrevious: true },
    { text: "n) Optical pyrometer", page: 9, id: "next" },
  ];

  assert.deepEqual(mergeVisualRowContinuations(rows), [
    { text: "m) RHEED system description\nThe analysis software shall be integrated.", page: 8, id: "first" },
    { text: "n) Optical pyrometer", page: 9, id: "next" },
  ]);
});

test("keeps a row separate unless vision marks it as an adjacent-page continuation", () => {
  const rows = [
    { text: "Section heading", page: 8 },
    { text: "a) New requirement", page: 9, continuationOfPrevious: false },
    { text: "another segment", page: 11, continuationOfPrevious: true },
  ];

  assert.deepEqual(mergeVisualRowContinuations(rows), rows);
});

test("drops a partial visual suggestion when a longer accepted quote already covers it", () => {
  const kept = discardContainedSuggestions(
    ["c) Effusion cells: Capacity ≥85 cm3, proper design for Ga."],
    [{ quote: "c) Effusion cells: Capacity" }, { quote: "a) Motorized phosphorus cracker source" }],
  );
  assert.deepEqual(kept, [{ quote: "a) Motorized phosphorus cracker source" }]);
});

test("keeps an exact source cell even when its wording is contained in another requirement", () => {
  assert.equal(keepParsedSourceCandidate(
    { quote: "thick steel", source_cells_exact: true },
    ["Trussed honeycomb, made with 0.25 mm or more thick steel sheet materials"],
  ), true);
  assert.equal(keepParsedSourceCandidate(
    { quote: "partial summary" },
    ["A longer requirement containing partial summary"],
  ), false);
});

test("does not deduplicate equal specification text from different source rows", () => {
  assert.notEqual(
    sourceCandidateKey(23, "6 EA", ["3", "Number of Isolators", "6 EA"]),
    sourceCandidateKey(23, "6 EA", ["4", "Leveling Valves", "6 EA"]),
  );
  assert.equal(
    sourceCandidateKey(23, "6 EA", ["3", "Number of Isolators", "6 EA"]),
    sourceCandidateKey(23, " 6 EA ", ["3", "Number of Isolators", "6 EA"]),
  );
});

test("keeps a separately formatted section heading contained in a larger source quote", () => {
  const kept = discardContainedSuggestions(
    ["Accessories and Attachments Wide Frame Option WF850-300kN: Wide frame"],
    [{ quote: "Accessories and Attachments", row_type: "section" }],
  );
  assert.deepEqual(kept, [{ quote: "Accessories and Attachments", row_type: "section" }]);
});

test("accepts AI row splits only when the literal parts cover the full source cell", () => {
  const source = "6. Control system Cabinets are included. Logging is provided.";
  assert.deepEqual(splitSourceQuote(source, ["6. Control system Cabinets are included.", "Logging is provided."]), [
    "6. Control system Cabinets are included.",
    "Logging is provided.",
  ]);
  assert.deepEqual(splitSourceQuote(source, ["6. Control system Cabinets are included."]), [source]);
  assert.deepEqual(splitSourceQuote(source, ["6. Control system Cabinets are included.", "Logging"]), [source]);
});

test("accepts separate lettered checks only when all source text is retained in order", () => {
  const source = "c) Check uniformity by XRD. d) Check Hall mobility. e) Show cracker efficiency.";
  assert.deepEqual(splitSourceQuote(source, [
    "c) Check uniformity by XRD.",
    "d) Check Hall mobility.",
    "e) Show cracker efficiency.",
  ]), [
    "c) Check uniformity by XRD.",
    "d) Check Hall mobility.",
    "e) Show cracker efficiency.",
  ]);
  assert.deepEqual(splitSourceQuote(source, ["c) Check uniformity by XRD.", "e) Show cracker efficiency."]), [source]);
});


test('case-sensitive units remain distinct during recovery and source candidate deduplication',()=>{
 const milli={page:2,quote:'Optical power shall be 1 mW.'};
 const mega={page:2,quote:'Optical power shall be 1 MW.'};
 assert.deepEqual(discardContainedSuggestionsByPage([milli],[mega]),[mega]);
 assert.notEqual(sourceCandidateKey(2,milli.quote),sourceCandidateKey(2,mega.quote));
 assert.deepEqual(discardContainedSuggestions(['Limit: Optical power shall be 1 mW.'],[mega]),[mega]);
});
