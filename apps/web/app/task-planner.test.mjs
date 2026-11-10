import assert from "node:assert/strict";
import test from "node:test";
import { bindTaskPlanToInventory, buildPlannedInspectionWorkUnits, buildTaskPlanRequest, maskExecutedOcrRegions, maskExecutedTextBlockSpans, requestTaskPlan, selectTaskPlanRegions, validateTaskPlanEnvelope } from "./task-planner.ts";

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
  const regionKinds = new Map(request.pages.flatMap((page) => page.regions.map((region) => [region.sourceId, region.kind])));
  return validateTaskPlanEnvelope(
    plan,
    request,
    pageIds,
    [...regionPageIds.keys()],
    regionPageIds,
    new Set(request.pages.filter((page) => page.unrepresentedRegionCount > 0 || page.clippedRegionCount > 0 || page.excerptClipped
        || (page.hasRasterImageContent && (!page.regions.some((region) => region.kind.startsWith("ocr_"))
          || page.regions.some((region) => region.kind.startsWith("image_") && region.kind !== "image_text-found")))).map((page) => page.sourceId)),
    regionKinds,
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

test("rejects inspection modes incompatible with parser-owned region kinds and duplicate work", () => {
  const incompatible = validPlan();
  incompatible.proposal.actions[0].mode = "visual";
  assert.deepEqual(validate(incompatible), { ok: false, error: "invalid_action" });

  const overlapping = validPlan();
  overlapping.proposal.actions.push({ mode: "native_text", sourceIds: ["doc:page:1:text:1"], rationale: "Repeat the source action." });
  assert.deepEqual(validate(overlapping), { ok: false, error: "invalid_action" });
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
  assert.equal(result.pages[0].unrepresentedRegionCount, 3);
  assert.equal(result.pages[0].clippedRegionCount, 2);
  assert.ok(result.pages[0].regions.every((region) => region.excerpt.length <= 120));
  assert.ok(result.pages[0].regions.some((region) => region.sourceId === "doc:page:1:text:1"));
});

test("bounded planner inventory keeps table, OCR, and image sources visible on dense text pages", () => {
  const page = {
    id: "doc:page:1",
    physicalPdfPageNumber: 1,
    hasRasterImageContent: true,
    ocrStatus: "text-found",
    imageRegions: [{ id: "doc:page:1:image:1" }],
    ocrRegions: [{ id: "doc:page:1:ocr:1", text: "Scanned annotation", confidenceLevel: "medium" }],
    textBlocks: Array.from({ length: 20 }, (_, index) => ({ id: `doc:page:1:text:${index + 1}`, text: `Text item ${index + 1}` })),
    tables: [{ id: "doc:page:1:table:1", rows: [{ id: "doc:page:1:table:1:row:1", cells: [{ id: "doc:page:1:table:1:row:1:cell:1", sourceText: "Required value 1 mm" }] }] }],
  };
  const result = buildTaskPlanRequest({ document: { fingerprint, pages: [page] }, pageText: new Map([[1, "Tender page summary"]]), runId: "run_test" });
  const selectedIds = result.pages[0].regions.map((region) => region.sourceId);
  assert.equal(selectedIds.length, 6);
  assert.ok(selectedIds.includes("doc:page:1:text:1"), "The planner retains an executable native-text source");
  assert.ok(selectedIds.includes("doc:page:1:table:1"), "A dense text layer cannot hide a parser-owned table");
  assert.ok(selectedIds.includes("doc:page:1:table:1:row:1"), "A source row remains available for a focused table action");
  assert.ok(selectedIds.includes("doc:page:1:ocr:1"), "OCR-derived evidence remains visible beside native text");
  assert.ok(selectedIds.includes("doc:page:1:image:1"), "Visual-only source regions remain visible beside native text");
  assert.equal(result.pages[0].unrepresentedRegionCount, result.pages[0].regionCount - selectedIds.length);
  assert.deepEqual(selectTaskPlanRegions([{ kind: "native_text_block" }, { kind: "table" }, { kind: "ocr_high" }], 2), [
    { kind: "native_text_block" }, { kind: "table" },
  ]);
  assert.throws(() => selectTaskPlanRegions([], -1), /non-negative integer/);
});

test("removes only executed parser spans from the legacy fallback and preserves page offsets", () => {
  const source = "First obligation\nSelected block\nThird obligation";
  const startOffset = source.indexOf("Selected block");
  const endOffset = startOffset + "Selected block".length;
  const fallback = maskExecutedTextBlockSpans(source, [{ startOffset, endOffset }]);
  assert.equal(fallback.slice(0, "First obligation".length), "First obligation");
  assert.equal(fallback.slice(startOffset, endOffset), " ".repeat("Selected block".length));
  assert.equal(fallback.slice(fallback.indexOf("Third obligation")), "Third obligation");
  assert.equal(fallback.length, source.length);
  assert.throws(() => maskExecutedTextBlockSpans(source, [{ startOffset: -1, endOffset: 3 }]), /invalid source span/);
});

test("masks only planner-executed OCR regions while preserving transcript offsets", () => {
  const regions = [
    { id: "ocr:1", text: "First OCR obligation" },
    { id: "ocr:2", text: "Selected OCR obligation" },
    { id: "ocr:3", text: "Third OCR obligation" },
  ];
  const transcript = regions.map((region) => region.text).join("\n");
  const start = transcript.indexOf(regions[1].text);
  const masked = maskExecutedOcrRegions(transcript, regions, new Set(["ocr:2"]));
  assert.equal(masked.length, transcript.length);
  assert.equal(masked.slice(start, start + regions[1].text.length), " ".repeat(regions[1].text.length));
  assert.ok(masked.includes(regions[0].text));
  assert.ok(masked.includes(regions[2].text));
});

test("binds scope and inspection actions to parser-owned physical pages", () => {
  const document = { pages: [
      { id: "doc:page:1", physicalPdfPageNumber: 1, imageRegions: [], ocrRegions: [], textBlocks: [{ id: "doc:page:1:text:1", text: "selected block", startOffset: 10, endOffset: 24 }], tables: [] },
      { id: "doc:page:2", physicalPdfPageNumber: 2, imageRegions: [{ id: "doc:page:2:image:1", ocrDisposition: "failed" }], ocrRegions: [], textBlocks: [], tables: [] },
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

test("materializes validated actions as stable source-ordered work units", () => {
  const proposal = validPlan().proposal;
  const sourceIdToNumber = new Map([
    ["doc:page:1", 1], ["doc:page:1:text:1", 1], ["doc:page:2", 2], ["doc:page:2:image:1", 2],
  ]);
  const sourceKinds = new Map([["doc:page:1:text:1", "native_text_block"], ["doc:page:2:image:1", "image_failed"]]);
  const first = buildPlannedInspectionWorkUnits({ runId: request.runId, proposal, sourceIdToNumber, sourceKinds, createdAt: "2026-11-10T10:00:00.000Z" });
  const second = buildPlannedInspectionWorkUnits({ runId: request.runId, proposal: { ...proposal, actions: [...proposal.actions].reverse() }, sourceIdToNumber, sourceKinds, createdAt: "2026-11-10T10:00:00.000Z" });
  assert.deepEqual(first.map(({ unit }) => unit.idempotencyKey), second.map(({ unit }) => unit.idempotencyKey));
  assert.deepEqual(first.map(({ physicalPage }) => physicalPage), [1, 2]);
  assert.deepEqual(first.map(({ mode }) => mode), ["native_text", "visual"]);
  assert.match(first[0].unit.operation, /^planned_native_text_extraction:/);
  assert.equal(first[1].unit.operation, "visual");
  assert.throws(() => buildPlannedInspectionWorkUnits({ runId: request.runId, proposal, sourceIdToNumber: new Map(), sourceKinds, createdAt: "2026-11-10T10:00:00.000Z" }), /outside the validated inventory/);
});

test("materializes selected OCR regions as persisted extraction work", () => {
  const proposal = { ...validPlan().proposal, actions: [{ mode: "ocr", sourceIds: ["doc:page:2:ocr:1"], rationale: "Inspect this OCR transcript." }] };
  const work = buildPlannedInspectionWorkUnits({
    runId: request.runId,
    proposal,
    sourceIdToNumber: new Map([["doc:page:2:ocr:1", 2]]),
    sourceKinds: new Map([["doc:page:2:ocr:1", "ocr_high"]]),
    createdAt: "2026-11-10T10:00:00.000Z",
  });
  assert.equal(work.length, 1);
  assert.equal(work[0].unit.kind, "extract");
  assert.match(work[0].unit.operation, /^planned_ocr_extraction:/);
  assert.deepEqual(work[0].unit.sourceIds, ["doc:page:2:ocr:1"]);
});
