import test from "node:test";
import assert from "node:assert/strict";
import { groupSourceObligationCandidates, orderCandidatesBySourceObligationGroups } from "./source-obligation-grouping.ts";

const fingerprint = "a1b2c3d4e5f60718293a";
const parentQuote = "The quote must include a separate charge for a Five-year Annual Maintenance Contract (AMC), covering:";
const items = [
  "Service visits;",
  "Yearly calibration;",
  "Routine maintenance services,",
  "and Provision of spare parts and necessary consumables",
];

function candidatesFor(sourceText, quotes = [parentQuote, ...items]) {
  return quotes.map((quote, index) => {
    const startOffset = sourceText.indexOf(quote);
    return {
      candidateId: `candidate-${index + 1}`,
      page: 11,
      quote,
      sourceQuote: quote,
      rowType: index === 0 ? "instruction" : "requirement",
      sourceSpan: startOffset < 0 ? null : { startOffset, endOffset: startOffset + quote.length },
    };
  });
}

function group(sourceText, quotes) {
  const candidates = candidatesFor(sourceText, quotes);
  return groupSourceObligationCandidates({
    documentFingerprint: fingerprint,
    page: 11,
    sourceText,
    candidates,
    eligibleCandidateIds: new Set(candidates.map((candidate) => candidate.candidateId)),
  });
}

test("groups a complete source-ordered AMC list without combining its quotes", () => {
  const sourceText = `${parentQuote} ${items[0]} ${items[1]} ${items[2]} ${items[3]}\n○ The supplier must have a local office in India.`;
  const groups = group(sourceText);

  assert.equal(groups.length, 1);
  assert.equal(groups[0].id, `sog-${fingerprint.slice(0, 16)}-p11-o0`);
  assert.deepEqual(groups[0].members.map((member) => [member.candidateId, member.role, member.memberOrder]), [
    ["candidate-1", "parent", 0],
    ["candidate-2", "member", 1],
    ["candidate-3", "member", 2],
    ["candidate-4", "member", 3],
    ["candidate-5", "member", 4],
  ]);
  for (const member of groups[0].members) {
    const source = sourceText.slice(member.sourceSpan.startOffset, member.sourceSpan.endOffset);
    assert.equal(source, [parentQuote, ...items][member.memberOrder]);
  }
  assert.equal(groups[0].members.map((member) => sourceText.slice(member.sourceSpan.startOffset, member.sourceSpan.endOffset)).join(" ").includes("Five-year"), true);
});

test("uses a parser-owned standalone list marker and geometry when PDF.js maps the bullet to o", () => {
  const sourceText = `${parentQuote} ${items[0]} ${items[1]} ${items[2]} ${items[3]} o The supplier must have local support.`;
  const candidates = candidatesFor(sourceText);
  const markerStart = sourceText.lastIndexOf(" o The") + 1;
  const marker = { id: "page-11:text:39", text: "o", startOffset: markerStart, endOffset: markerStart + 1, bbox: { x: 20, y: 10, width: 4, height: 5 } };
  const next = { id: "page-11:text:41", text: "The", startOffset: markerStart + 2, endOffset: markerStart + 5, bbox: { x: 50, y: 10, width: 10, height: 5 } };
  const result = groupSourceObligationCandidates({
    documentFingerprint: fingerprint,
    page: 11,
    sourceText,
    sourceElements: [marker, next],
    candidates,
    eligibleCandidateIds: new Set(candidates.map((candidate) => candidate.candidateId)),
  });
  assert.equal(result.length, 1);
  assert.equal(result[0].members.length, 5);

  const nonBulletElements = [
    marker,
    { ...next, bbox: { ...next.bbox, x: 20 } },
  ];
  assert.deepEqual(groupSourceObligationCandidates({
    documentFingerprint: fingerprint,
    page: 11,
    sourceText,
    sourceElements: nonBulletElements,
    candidates,
    eligibleCandidateIds: new Set(candidates.map((candidate) => candidate.candidateId)),
  }), []);
});

test("does not group a partial list when an unextracted source item lies between candidates", () => {
  const sourceText = `${parentQuote} ${items[0]} ${items[1]} ${items[2]} ${items[3]}\n○ Separate local-support clause.`;
  const partial = [parentQuote, items[0], items[1], items[2]];
  assert.deepEqual(group(sourceText, partial), []);
});

test("does not merge separate nearby service clauses without an exact list introducer", () => {
  const first = "The supplier must provide yearly calibration.";
  const second = "The supplier must provide service visits.";
  const sourceText = `${first}\n○ ${second}`;
  assert.deepEqual(group(sourceText, [first, second]), []);
});

test("does not group bidder-form warranty or service-centre declarations", () => {
  const formLines = ["Warranty period agreed", "Service Centre details:", "Contact person, telephone and e-mail"];
  const sourceText = formLines.join("\n○ ");
  assert.deepEqual(group(sourceText, formLines), []);
});

test("requires unique exact source spans and refuses duplicated or inconsistent quotes", () => {
  const sourceText = `${parentQuote} ${items.join(" ")}\n○ ${items[1]}`;
  assert.deepEqual(group(sourceText), []);

  const cleanText = `${parentQuote} ${items.join(" ")}\n○ The supplier must provide local support.`;
  const candidates = candidatesFor(cleanText);
  candidates[2].sourceSpan = { startOffset: candidates[2].sourceSpan.startOffset + 1, endOffset: candidates[2].sourceSpan.endOffset + 1 };
  assert.deepEqual(groupSourceObligationCandidates({
    documentFingerprint: fingerprint,
    page: 11,
    sourceText: cleanText,
    candidates,
    eligibleCandidateIds: new Set(candidates.map((candidate) => candidate.candidateId)),
  }), []);
});

test("keeps groups within one page and an explicitly eligible source set", () => {
  const sourceText = `${parentQuote} ${items.join(" ")}\n○ The supplier must provide local support.`;
  const candidates = candidatesFor(sourceText);
  candidates[4].page = 12;
  const result = groupSourceObligationCandidates({
    documentFingerprint: fingerprint,
    page: 11,
    sourceText,
    candidates,
    eligibleCandidateIds: new Set(candidates.slice(0, 4).map((candidate) => candidate.candidateId)),
  });
  assert.deepEqual(result, []);
});

test("keeps validated group rows together in source order without reordering unrelated candidates", () => {
  const sourceText = `${parentQuote} ${items[0]} ${items[1]} ${items[2]} ${items[3]}\n○ The supplier must provide local support.`;
  const candidates = candidatesFor(sourceText);
  const groups = groupSourceObligationCandidates({
    documentFingerprint: fingerprint,
    page: 11,
    sourceText,
    candidates,
    eligibleCandidateIds: new Set(candidates.map((candidate) => candidate.candidateId)),
  });
  const queue = [
    { id: "outside-before" },
    candidates[2],
    { id: "unrelated-interleaved" },
    candidates[0],
    candidates[4],
    candidates[1],
    candidates[3],
    { id: "outside-after" },
  ];
  const ordered = orderCandidatesBySourceObligationGroups({
    candidates: queue,
    groups,
    candidateId: (candidate) => "candidateId" in candidate ? candidate.candidateId : undefined,
  });
  assert.deepEqual(ordered.map((candidate) => "candidateId" in candidate ? candidate.candidateId : candidate.id), [
    "outside-before",
    "candidate-1",
    "candidate-2",
    "candidate-3",
    "candidate-4",
    "candidate-5",
    "unrelated-interleaved",
    "outside-after",
  ]);
});

test("does not treat an abrupt PDF page end as proof the service list is complete", () => {
  // A cross-page list is not safely complete when all the extractor saw was
  // the first child and then the end of the current physical page's text.
  const sourceText = `${parentQuote} ${items[0]}`;
  assert.deepEqual(group(sourceText, [parentQuote, items[0]]), []);
});

test("rejects an apparent boundary that actually introduces another list item", () => {
  const sourceText = `${parentQuote} ${items[0]}\n○ ${items[1]}\n○ ${items[2]}`;
  assert.deepEqual(group(sourceText, [parentQuote, items[0], items[1], items[2]]), []);
  // Even with an unextracted child, the bullet is not proof of list completion.
  assert.deepEqual(group(sourceText, [parentQuote, items[0]]), []);
});
