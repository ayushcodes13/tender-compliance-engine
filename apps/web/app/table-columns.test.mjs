import assert from "node:assert/strict";
import test from "node:test";
import { chooseRequirementColumn } from "./table-columns.ts";

test("uses the model's specification role in a dynamic table", () => {
  assert.equal(chooseRequirementColumn([
    { header: "S. No.", role: "serial" },
    { header: "Specification", role: "heading" },
    { header: "Description", role: "specification" },
    { header: "Comply", role: "compliance" },
    { header: "Remarks", role: "remark" },
  ], [["1", "Thickness", "≥ 300 mm", "", ""]]), 2);
});

test("falls back to the semantically labeled description column if role classification is incomplete", () => {
  assert.equal(chooseRequirementColumn([
    { header: "Sr No", role: "serial" },
    { header: "Parameter", role: "heading" },
    { header: "Description", role: "other" },
    { header: "Comply", role: "compliance" },
  ], [["1", "Thickness", "≥ 300 mm", ""]]), 2);
});

test("falls back to the text-rich eligible column without fixed column-count assumptions", () => {
  assert.equal(chooseRequirementColumn([
    { header: "No.", role: "serial" },
    { header: "Item", role: "heading" },
    { header: "Min", role: "other" },
    { header: "Maximum", role: "other" },
    { header: "Remarks", role: "remark" },
  ], [["1", "Pressure", "80 psi", "120 psi", ""]]), 2);
});
