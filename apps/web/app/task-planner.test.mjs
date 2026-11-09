import assert from "node:assert/strict";
import test from "node:test";
import { bindTaskPlanToInventory, buildTaskPlanRequest, requestTaskPlan, validateTaskPlanEnvelope } from "./task-planner.ts";

const fingerprint = "f".repeat(64);
const request = {
  schemaVersion: 1,
  runId: "run_test",
  sourceFingerprint: fingerprint,
  task: "Prepare a technical response matrix from this tender.",
  pages: [
    { sourceId: "doc:page:1", physicalPage: 1, excerpt: "Technical requirements", excerptClipped: false, hasRasterImageContent: false, ocrStatus: "not-recommended", tableCount: 1, tableRowCount: 2 },
    { sourceId: "doc:page:2", physicalPage: 2, excerpt: "Scanned page", excerptClipped: true, hasRasterImageContent: true, ocrStatus: "failed", tableCount: 0, tableRowCount: 0 },
  ],
};
const validPlan = () => ({
  schemaVersion: 1,
  runId: request.runId,
  sourceFingerprint: fingerprint,
  proposal: {
    task: request.task,
    scope: [
      { sourceIds: ["doc:page:1"], disposition: "relevant", rationale: "Contains specifications." },
      { sourceIds: ["doc:page:2"], disposition: "unresolved", rationale: "Image text is not readable." },
    ],
    sections: [{ label: "Technical requirements", sourceIds: ["doc:page:1"] }],
    actions: [{ mode: "table", sourceIds: ["doc:page:1"], rationale: "Inspect the detected schedule." }, { mode: "visual", sourceIds: ["doc:page:2"], rationale: "Inspect the unresolved scan." }],
    openQuestions: ["Does the scanned page continue the schedule?"],
  },
});

test("validates a source-bound plan that accounts for each supplied page", () => {
  const result = validateTaskPlanEnvelope(validPlan(), request, request.pages.map(({ sourceId }) => sourceId));
  assert.equal(result.ok, true);
  assert.equal(result.plan.proposal.scope.length, 2);
  assert.deepEqual(result.plan.proposal.actions.map(({ mode }) => mode), ["table", "visual"]);
});

test("rejects stale envelopes, invented IDs, missing scope, and duplicate page scope", () => {
  const stale = validPlan(); stale.sourceFingerprint = "0".repeat(64);
  assert.deepEqual(validateTaskPlanEnvelope(stale, request, request.pages.map(({ sourceId }) => sourceId)), { ok: false, error: "invalid_envelope" });

  const invented = validPlan(); invented.proposal.scope[0].sourceIds = ["doc:page:999"];
  assert.deepEqual(validateTaskPlanEnvelope(invented, request, request.pages.map(({ sourceId }) => sourceId)), { ok: false, error: "unknown_source_id" });

  const missing = validPlan(); missing.proposal.scope.pop();
  assert.deepEqual(validateTaskPlanEnvelope(missing, request, request.pages.map(({ sourceId }) => sourceId)), { ok: false, error: "missing_page_scope" });

  const duplicate = validPlan(); duplicate.proposal.scope[1].sourceIds = ["doc:page:1"];
  assert.deepEqual(validateTaskPlanEnvelope(duplicate, request, request.pages.map(({ sourceId }) => sourceId)), { ok: false, error: "duplicate_page_scope" });
});

test("rejects unsupported modes and plans exceeding bounded operation limits", () => {
  const unsupported = validPlan(); unsupported.proposal.actions[0].mode = "run_shell";
  assert.deepEqual(validateTaskPlanEnvelope(unsupported, request, request.pages.map(({ sourceId }) => sourceId)), { ok: false, error: "invalid_action" });

  const tooManySources = validPlan();
  const extraPages = Array.from({ length: 12 }, (_, i) => `doc:page:${i + 3}`);
  tooManySources.proposal.scope.push(...extraPages.map((sourceId) => ({ sourceIds: [sourceId], disposition: "relevant", rationale: "Included in the bounded-action test." })));
  tooManySources.proposal.actions[0].sourceIds = ["doc:page:1", ...extraPages];
  assert.deepEqual(validateTaskPlanEnvelope(tooManySources, request, [...request.pages.map(({ sourceId }) => sourceId), ...extraPages]), { ok: false, error: "invalid_action" });
});

test("does not allow an excluded page to also receive an inspection action", () => {
  const inconsistent = validPlan();
  inconsistent.proposal.scope[0].disposition = "outside_task";
  assert.deepEqual(validateTaskPlanEnvelope(inconsistent, request, request.pages.map(({ sourceId }) => sourceId)), { ok: false, error: "invalid_action" });
});

test("builds page-level summaries with source IDs, modality state, and explicit clipping", () => {
  const document = {
    fingerprint,
    pages: [
      { id: "doc:page:1", physicalPdfPageNumber: 1, hasRasterImageContent: false, ocrStatus: "not-recommended", tables: [{ rows: [{}, {}] }] },
    ],
  };
  const result = buildTaskPlanRequest({ document, pageText: new Map([[1, "x".repeat(700)]]), runId: "run_test" });
  assert.equal(result.pages[0].sourceId, "doc:page:1");
  assert.equal(result.pages[0].excerpt.length, 600);
  assert.equal(result.pages[0].excerptClipped, true);
  assert.equal(result.pages[0].tableRowCount, 2);
});

test("binds scope and inspection actions to parser-owned physical pages", () => {
  const document = { pages: [
    { id: "doc:page:1", physicalPdfPageNumber: 1 },
    { id: "doc:page:2", physicalPdfPageNumber: 2 },
  ] };
  const plan = validPlan().proposal;
  const bound = bindTaskPlanToInventory(document, plan);
  assert.deepEqual(bound.proposedExcludedPageNumbers, []);
  assert.deepEqual(bound.actionPageNumbers, [1, 2]);

  plan.scope[1].disposition = "outside_task";
  assert.throws(() => bindTaskPlanToInventory(document, plan), /outside its validated page scope/);
  plan.actions = plan.actions.filter((action) => !action.sourceIds.includes("doc:page:2"));
  const withExclusion = bindTaskPlanToInventory(document, plan);
  assert.deepEqual(withExclusion.proposedExcludedPageNumbers, [2]);
  assert.deepEqual(bindTaskPlanToInventory(document, plan).proposedExcludedPageNumbers, [2]);
});

test("requests and validates a plan through the injected model adapter", async () => {
  const plan = validPlan();
  let called = false;
  const result = await requestTaskPlan({
    request,
    model: "gpt-6-luna",
    endpoint: "https://model.invalid/chat/completions",
    fetcher: async (url, init) => {
      called = true;
      assert.equal(String(url), "https://model.invalid/chat/completions");
      const body = JSON.parse(init.body);
      assert.equal(body.response_format.json_schema.name, "tender_task_plan");
      assert.match(body.messages[0].content, /untrusted/);
      return Response.json({ choices: [{ message: { content: JSON.stringify(plan) } }] });
    },
  });
  assert.equal(called, true);
  assert.equal(result.ok, true);
  assert.equal(result.plan.runId, request.runId);
});
