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
    { sourceId: "doc:page:1", physicalPage: 1, excerpt: "Technical requirements", excerptClipped: false, regions: [{ sourceId: "doc:page:1:text:1", kind: "native_text_block", excerpt: "Technical requirements", excerptClipped: false }], regionCount: 1, unrepresentedRegionCount: 0, clippedRegionCount: 0, hasRasterImageContent: false, ocrStatus: "not-recommended", tableCount: 1, tableRowCount: 2 },
    { sourceId: "doc:page:2", physicalPage: 2, excerpt: "Scanned page", excerptClipped: true, regions: [{ sourceId: "doc:page:2:image:1", kind: "image_failed", excerpt: "", excerptClipped: false }], regionCount: 1, unrepresentedRegionCount: 0, clippedRegionCount: 0, hasRasterImageContent: true, ocrStatus: "failed", tableCount: 0, tableRowCount: 0 },
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
    sections: [{ label: "Technical requirements", sourceIds: ["doc:page:1:text:1"] }],
    actions: [{ mode: "native_text", sourceIds: ["doc:page:1:text:1"], rationale: "Inspect the technical text block." }, { mode: "visual", sourceIds: ["doc:page:2:image:1"], rationale: "Inspect the unresolved scan region." }],
    openQuestions: ["Does the scanned page continue the schedule?"],
  },
});

const validate = (plan, extraPageIds = []) => {
  const pageIds = [...request.pages.map(({ sourceId }) => sourceId), ...extraPageIds];
  const regionPageIds = new Map(request.pages.flatMap((page) => page.regions.map((region) => [region.sourceId, page.sourceId])));
  return validateTaskPlanEnvelope(
    plan,
    request,
    pageIds,
    [...regionPageIds.keys()],
    regionPageIds,
    new Set(request.pages.filter((page) => page.unrepresentedRegionCount > 0 || page.clippedRegionCount > 0 || page.excerptClipped
      || (page.hasRasterImageContent && (!page.regions.some((region) => region.kind.startsWith("ocr_"))
        || page.regions.some((region) => region.kind.startsWith("image_") && region.kind !== "image_text-found")))).map((page) => page.sourceId)),
  );
};

test("validates a source-bound plan that accounts for each supplied page", () => {
  const result = validate(validPlan());
  assert.equal(result.ok, true);
  assert.equal(result.plan.proposal.scope.length, 2);
  assert.deepEqual(result.plan.proposal.actions.map(({ mode }) => mode), ["native_text", "visual"]);
});

test("rejects stale envelopes, invented IDs, missing scope, and duplicate page scope", () => {
  const stale = validPlan(); stale.sourceFingerprint = "0".repeat(64);
  assert.deepEqual(validate(stale), { ok: false, error: "invalid_envelope" });

  const invented = validPlan(); invented.proposal.scope[0].sourceIds = ["doc:page:999"];
  assert.deepEqual(validate(invented), { ok: false, error: "unknown_source_id" });

  const missing = validPlan(); missing.proposal.scope.pop();
  assert.deepEqual(validate(missing), { ok: false, error: "missing_page_scope" });

  const duplicate = validPlan(); duplicate.proposal.scope[1].sourceIds = ["doc:page:1"];
  assert.deepEqual(validate(duplicate), { ok: false, error: "duplicate_page_scope" });
});

test("rejects unsupported modes and plans exceeding bounded operation limits", () => {
  const unsupported = validPlan(); unsupported.proposal.actions[0].mode = "run_shell";
  assert.deepEqual(validate(unsupported), { ok: false, error: "invalid_action" });

  const tooManySources = validPlan();
  const extraPages = Array.from({ length: 12 }, (_, i) => `doc:page:${i + 3}`);
  tooManySources.proposal.scope.push(...extraPages.map((sourceId) => ({ sourceIds: [sourceId], disposition: "relevant", rationale: "Included in the bounded-action test." })));
  tooManySources.proposal.actions[0].sourceIds = ["doc:page:1", ...extraPages];
  assert.deepEqual(validate(tooManySources, extraPages), { ok: false, error: "invalid_action" });
});

test("does not allow an excluded page to also receive an inspection action", () => {
  const inconsistent = validPlan();
  inconsistent.proposal.scope[0].disposition = "outside_task";
  assert.deepEqual(validate(inconsistent), { ok: false, error: "invalid_action" });
});

test("does not allow clipped page context to be classified outside the task", () => {
  const clipped = validPlan();
  clipped.proposal.scope[1].disposition = "outside_task";
  clipped.proposal.actions = clipped.proposal.actions.filter((action) => !action.sourceIds.includes("doc:page:2:image:1"));
  assert.deepEqual(validate(clipped), { ok: false, error: "invalid_envelope" });
});

test("does not allow an unreadable raster-only page to be excluded", () => {
  const plan = validPlan();
  plan.proposal.scope[1].disposition = "outside_task";
  plan.proposal.actions = plan.proposal.actions.filter((action) => !action.sourceIds.includes("doc:page:2:image:1"));
  assert.deepEqual(validate(plan), { ok: false, error: "invalid_envelope" });
});

test("rejects model actions that invent region IDs", () => {
  const plan = validPlan();
  plan.proposal.actions[0].sourceIds = ["doc:page:1:table:999:cell:1"];
  assert.deepEqual(validate(plan), { ok: false, error: "unknown_source_id" });
});

test("builds bounded page and region summaries with modality state and explicit clipping", () => {
  const document = {
    fingerprint,
    pages: [
      { id: "doc:page:1", physicalPdfPageNumber: 1, hasRasterImageContent: false, ocrStatus: "not-recommended", imageRegions: [{ id: "doc:page:1:image:1" }, { id: "doc:page:1:image:2" }], ocrRegions: [], textBlocks: [{ id: "doc:page:1:text:1", text: "Region sample" }, { id: "doc:page:1:text:2", text: "Second region" }], tables: [{ id: "doc:page:1:table:1", rows: [{ id: "doc:page:1:table:1:row:1", cells: [{ id: "doc:page:1:table:1:row:1:cell:1", sourceText: "V".repeat(121) }] }, { id: "doc:page:1:table:1:row:2", cells: [{ id: "doc:page:1:table:1:row:2:cell:1", sourceText: "Value" }] }] }] },
    ],
  };
  const result = buildTaskPlanRequest({ document, pageText: new Map([[1, "x".repeat(700)]]), runId: "run_test" });
  assert.equal(result.pages[0].sourceId, "doc:page:1");
  assert.equal(result.pages[0].excerpt.length, 600);
  assert.equal(result.pages[0].excerptClipped, true);
  assert.equal(result.pages[0].tableRowCount, 2);
  assert.equal(result.pages[0].regions.length, 6);
  assert.equal(result.pages[0].unrepresentedRegionCount, 1);
  assert.equal(result.pages[0].clippedRegionCount, 3);
  assert.ok(result.pages[0].regions.every((region) => region.excerpt.length <= 120));
  assert.ok(result.pages[0].regions.some((region) => region.sourceId.endsWith("cell:1")));
});

test("binds scope and inspection actions to parser-owned physical pages", () => {
  const document = { pages: [
    { id: "doc:page:1", physicalPdfPageNumber: 1, imageRegions: [], ocrRegions: [], textBlocks: [{ id: "doc:page:1:text:1" }], tables: [] },
    { id: "doc:page:2", physicalPdfPageNumber: 2, imageRegions: [{ id: "doc:page:2:image:1" }], ocrRegions: [], textBlocks: [], tables: [] },
  ] };
  const plan = validPlan().proposal;
  const bound = bindTaskPlanToInventory(document, plan);
  assert.deepEqual(bound.proposedExcludedPageNumbers, []);
  assert.deepEqual(bound.actionPageNumbers, [1, 2]);

  plan.scope[1].disposition = "outside_task";
  assert.throws(() => bindTaskPlanToInventory(document, plan), /outside its validated page scope/);
  plan.actions = plan.actions.filter((action) => !action.sourceIds.includes("doc:page:2:image:1"));
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

test("marks pages with omitted parser regions unresolved and binds region actions to parent pages", () => {
  const plan = validPlan();
  plan.proposal.scope[0].disposition = "outside_task";
  request.pages[0].unrepresentedRegionCount = 1;
  assert.deepEqual(validate(plan), { ok: false, error: "invalid_envelope" });
  request.pages[0].unrepresentedRegionCount = 0;

  const valid = validPlan().proposal;
  const bound = bindTaskPlanToInventory({ pages: [
    { id: "doc:page:1", physicalPdfPageNumber: 1, imageRegions: [], ocrRegions: [], textBlocks: [{ id: "doc:page:1:text:1" }], tables: [] },
    { id: "doc:page:2", physicalPdfPageNumber: 2, imageRegions: [{ id: "doc:page:2:image:1" }], ocrRegions: [], textBlocks: [], tables: [] },
  ] }, valid);
  assert.deepEqual(bound.actionPageNumbers, [1, 2]);
});
