import test from "node:test";
import assert from "node:assert/strict";
import { classifyInstructionCandidate } from "./candidate-classification.ts";
import { CandidateTraceLedger } from "./candidate-trace.ts";

const iitgServiceAnchorGroups = [
  "a separate charge for a Five-year Annual Maintenance Contract (AMC); Service visits; Yearly calibration; Routine maintenance services",
  "a local office or an authorized associate in India for timely after-sales support and maintenance",
  "availability of spare parts for a minimum period of five years beyond the initial warranty period",
];

test("retains the IIT Guwahati page-11 supplier service obligations when labeled instruction", () => {
  for (const sourceQuote of iitgServiceAnchorGroups) {
    const result = classifyInstructionCandidate("instruction", sourceQuote);
    assert.notEqual(result.outcome, "rejected", sourceQuote);
    assert.equal(result.effectiveRowType, "requirement", sourceQuote);
    assert.equal(result.requiresHumanReview, true, sourceQuote);
    assert.ok(["reclassified_for_review", "retained_for_review"].includes(result.outcome), sourceQuote);
  }
});

test("excludes procurement mechanics, commercial terms, and document navigation", () => {
  const excluded = [
    ["instruction", "Earnest Money Deposit (EMD) shall accompany the bid."],
    ["instruction", "Payment will be released according to the payment schedule."],
    ["instruction", "The successful bidder shall furnish a bank guarantee."],
    ["instruction", "Tender submission must be completed before the closing date."],
    ["instruction", "Bidders must indicate compliance status in every row."],
    ["instruction", "Delivery schedule and liquidated damages apply to late delivery."],
    ["instruction", "The purchaser reserves the right to cancel the tender without notice."],
    ["header", "Technical Specifications | Comply | Remarks"],
  ];
  for (const [rowType, quote] of excluded) {
    const result = classifyInstructionCandidate(rowType, quote);
    assert.equal(result.outcome, "rejected", quote);
    assert.equal(result.requiresHumanReview, false, quote);
    assert.ok(result.reason.length > 0, quote);
  }
});

test("does not accept a single service, warranty, or maintenance keyword as sufficient", () => {
  for (const quote of ["Service information is available on request.", "Warranty is described in the brochure.", "Maintenance is discussed in this section."]) {
    const result = classifyInstructionCandidate("instruction", quote);
    assert.equal(result.outcome, "retained_for_review");
    assert.equal(result.effectiveRowType, "requirement");
    assert.equal(result.requiresHumanReview, true);
  }
});

test("keeps unresolved source structure separate from a technical obligation", () => {
  const result = classifyInstructionCandidate("ambiguous", "Unclear source row: Source layout cannot be resolved.");
  assert.equal(result.outcome, "retained_for_review");
  assert.equal(result.effectiveRowType, "ambiguous");
  assert.equal(result.requiresHumanReview, true);
});

test("records why a candidate was reclassified while retaining literal evidence and source identity", () => {
  const quote = iitgServiceAnchorGroups[0];
  const decision = classifyInstructionCandidate("instruction", quote);
  const ledger = new CandidateTraceLedger("iitg-source-fingerprint");
  const candidateId = ledger.register({
    page: 11,
    origin: "initial_extraction",
    modelQuote: quote,
    sourceQuote: quote,
    sourceQuoteStatus: "matched",
    sourceElementIds: ["page-11:text-fixture"],
  });
  ledger.recordClassification(candidateId, decision);
  ledger.terminate(candidateId, { disposition: "accepted", responsibleStage: "source_evidence_validation", finalRequirementId: "req-11" });
  const adminQuote = "Earnest Money Deposit (EMD) shall accompany the bid.";
  const adminDecision = classifyInstructionCandidate("instruction", adminQuote);
  const rejectedId = ledger.register({ page: 11, origin: "initial_extraction", modelQuote: adminQuote, sourceQuote: adminQuote, sourceQuoteStatus: "matched", sourceElementIds: ["page-11:text-admin"] });
  ledger.recordClassification(rejectedId, adminDecision);
  ledger.terminate(rejectedId, { disposition: "rejected", responsibleStage: "candidate_type_validation", rejectionCategory: "administrative_procurement_clause" });

  const record = ledger.records[0];
  assert.equal(record.modelQuote, quote);
  assert.equal(record.sourceQuote, quote);
  assert.deepEqual(record.sourceElementIds, ["page-11:text-fixture"]);
  assert.deepEqual(record.classificationDecision, decision);
  assert.equal(record.disposition, "accepted");
  assert.equal(record.finalRequirementId, "req-11");
  const rejectedRecord = ledger.records.find((item) => item.candidateId === rejectedId);
  assert.equal(rejectedRecord?.classificationDecision?.reason, "bid_security_or_tender_fee");
  assert.equal(rejectedRecord?.classificationDecision?.outcome, "rejected");
  assert.equal(rejectedRecord?.responsibleStage, "candidate_type_validation");
});
