import test from "node:test";
import assert from "node:assert/strict";
import { complianceRowHeightTwips, reflowComplianceText, splitHeadingPrefix, verticalMergeAt } from "./compliance-format.ts";

test("scales PDF cell heights to DOCX row heights and enforces compact minimums", () => {
  assert.equal(complianceRowHeightTwips(46.1, false), 889);
  assert.equal(complianceRowHeightTwips(23, false), 443);
  assert.equal(complianceRowHeightTwips(8, true), 236);
  assert.equal(complianceRowHeightTwips(undefined, false), 443);
});

test("reflows visual line wraps into a Word paragraph without changing words", () => {
  assert.equal(reflowComplianceText("The control system shall provide\nautomatic long-term logging."), "The control system shall provide automatic long-term logging.");
});

test("keeps separately listed material lines and explicit dash bullets", () => {
  assert.equal(reflowComplianceText("Materials:\nIn (7N grade) 500 grams\nGa (8N grade) 500 grams", true), "Materials:\nIn (7N grade) 500 grams\nGa (8N grade) 500 grams");
  assert.equal(reflowComplianceText("Dopant cells:\n- Silicon source\n- Carbon source"), "Dopant cells:\n- Silicon source\n- Carbon source");
});

test("keeps AI-separated lettered subitems on distinct display lines", () => {
  assert.equal(reflowComplianceText("r) At least two viewing ports.\ns) Suitable bake out facilities."), "r) At least two viewing ports.\ns) Suitable bake out facilities.");
});

test("splits a literal section heading from its description without changing text", () => {
  const text = "6. MBE process control system\nElectronic Cabinets for PID controllers.";
  const parts = splitHeadingPrefix(text, "6. MBE process control system");
  assert.deepEqual(parts, {
    heading: "6. MBE process control system",
    remainder: "\nElectronic Cabinets for PID controllers.",
  });
  assert.equal(`${parts?.heading}${parts?.remainder}`, text);
});

test("accepts source line wrapping between heading words", () => {
  const parts = splitHeadingPrefix("4. MBE\nsources - Vendor to provide...", "4. MBE sources");
  assert.deepEqual(parts, { heading: "4. MBE\nsources", remainder: " - Vendor to provide..." });
});

test("rejects a heading suggestion that is not a literal prefix", () => {
  assert.equal(splitHeadingPrefix("6. MBE process control system", "MBE process"), null);
  assert.equal(splitHeadingPrefix("MBE process control system", "6. MBE process"), null);
});

test("merges only adjacent repeated heading values", () => {
  const values = ["Universal Testing Machine", "Universal Testing Machine", "Accessories", "Accessories", "Load Cells"];
  assert.deepEqual(values.map((_, index) => verticalMergeAt(values, index)), ["restart", "continue", "restart", "continue", undefined]);
});
