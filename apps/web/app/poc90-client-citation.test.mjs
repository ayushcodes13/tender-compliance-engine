import test from "node:test";
import assert from "node:assert/strict";
import { visibleCitationEvidence, visibleCitationRequirement } from "./poc90-client-citation.ts";

const requirement = { page: 8, sourceReference: { sourceElementIds: ["page-8:text:12"], locationPrecision: "exact" } };

test("citation IDs show only for the requirement on the currently displayed physical page", () => {
  assert.deepEqual(visibleCitationEvidence(requirement, 8), {
    sourceElementIds: ["page-8:text:12"], approximate: false,
  });
  assert.equal(visibleCitationEvidence(requirement, 9), null);
  assert.equal(visibleCitationEvidence(null, 8), null);
});

test("coverage row inspection never borrows IDs or uncertainty from selected requirement", () => {
  assert.equal(visibleCitationEvidence(requirement, 8, 8), null);
  const approximate = { page: 8, sourceReference: { sourceElementIds: [], locationPrecision: "approximate" } };
  assert.equal(visibleCitationEvidence(approximate, 8, 8), null);
  assert.deepEqual(visibleCitationEvidence(approximate, 8), { sourceElementIds: [], approximate: true });
});

test("page-only inspection never shows a stale requirement from another physical page", () => {
  assert.equal(visibleCitationRequirement({ id: "p2", page: 2 }, 18), null);
  assert.deepEqual(visibleCitationRequirement({ id: "p18", page: 18 }, 18), { id: "p18", page: 18 });
  assert.equal(visibleCitationRequirement({ id: "p18", page: 18 }, 18, 18), null);
});
