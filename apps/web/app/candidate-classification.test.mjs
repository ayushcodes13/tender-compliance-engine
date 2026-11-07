import test from "node:test";
import assert from "node:assert/strict";
import { classifyCandidateScope } from "./candidate-classification.ts";
import { CandidateTraceLedger } from "./candidate-trace.ts";
import { collectSourceTableCoverageRows } from "./coverage-ledger.ts";

const iitgServiceAnchorGroups = [
  "a separate charge for a Five-year Annual Maintenance Contract (AMC); Service visits; Yearly calibration; Routine maintenance services",
  "a local office or an authorized associate in India for timely after-sales support and maintenance",
  "availability of spare parts for a minimum period of five years beyond the initial warranty period",
];

test("retains the IIT Guwahati page-11 supplier service obligations when labeled instruction", () => {
  for (const sourceQuote of iitgServiceAnchorGroups) {
    const result = classifyCandidateScope("instruction", sourceQuote);
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
    ["instruction", "The technical compliance report must be uploaded with the tender submission."],
    ["instruction", "Delivery schedule and liquidated damages apply to late delivery."],
    ["instruction", "The purchaser reserves the right to cancel the tender without notice."],
    ["header", "Technical Specifications | Comply | Remarks"],
  ];
  for (const [rowType, quote] of excluded) {
    const result = classifyCandidateScope(rowType, quote);
    assert.equal(result.outcome, "rejected", quote);
    assert.equal(result.requiresHumanReview, false, quote);
    assert.ok(result.reason.length > 0, quote);
  }
});

test("does not promote unmatched instruction candidates into requirements", () => {
  for (const quote of ["Service information is available on request.", "Warranty is described in the brochure.", "Maintenance is discussed in this section."]) {
    const result = classifyCandidateScope("instruction", quote);
    assert.equal(result.outcome, "retained_for_review");
    assert.equal(result.effectiveRowType, "ambiguous");
    assert.equal(result.requiresHumanReview, true);
  }
});

test("keeps a supplier-required calibration certificate despite the submission verb", () => {
  const quote = "The supplier shall submit calibration certificates.";
  const result = classifyCandidateScope("instruction", quote);
  assert.equal(result.outcome, "reclassified_for_review");
  assert.equal(result.effectiveRowType, "requirement");
  assert.equal(result.reason, "supplier_technical_document_submission");
  assert.equal(result.requiresHumanReview, true);
});

test("retains mixed administrative and supplier-service clauses as review-only with their source intact", () => {
  const quote = "The tender submission must include the bid form, and the supplier shall provide calibration certificates.";
  const result = classifyCandidateScope("instruction", quote);
  assert.equal(result.outcome, "retained_for_review");
  assert.equal(result.effectiveRowType, "ambiguous");
  assert.equal(result.reason, "mixed_administrative_and_supplier_obligation");
  assert.equal(result.requiresHumanReview, true);
  assert.ok(quote.includes("tender submission"));
  assert.ok(quote.includes("supplier shall provide calibration certificates"));
});

test("keeps unresolved source structure separate from a technical obligation", () => {
  const result = classifyCandidateScope("ambiguous", "Unclear source row: Source layout cannot be resolved.");
  assert.equal(result.outcome, "retained_for_review");
  assert.equal(result.effectiveRowType, "ambiguous");
  assert.equal(result.requiresHumanReview, true);
});

test("records why a candidate was reclassified while retaining literal evidence and source identity", () => {
  const quote = iitgServiceAnchorGroups[0];
  const decision = classifyCandidateScope("instruction", quote);
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
  ledger.recordClassification(candidateId, classifyCandidateScope("requirement", quote));
  ledger.terminate(candidateId, { disposition: "accepted", responsibleStage: "source_evidence_validation", finalRequirementId: "req-11" });
  const adminQuote = "Earnest Money Deposit (EMD) shall accompany the bid.";
  const adminDecision = classifyCandidateScope("instruction", adminQuote);
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

test("coverage keeps a review-only vector obligation visible without counting it as an excluded instruction", () => {
  const { rows } = collectSourceTableCoverageRows([
    {
      cells: ["The tender submission includes the bid form; supplier shall provide calibration certificates."],
      cellBoxes: [],
      bbox: null,
      sourceClassification: "ambiguous",
      originalSourceClassification: "instruction",
      classificationReason: "ambiguous_source_structure",
    },
  ], new Map([[0, 1]]), new Set(), { width: 100, height: 100 });

  assert.equal(rows[0].disposition, "candidate");
  assert.equal(rows[0].sourceClassification, "ambiguous");
  assert.equal(rows[0].originalSourceClassification, "instruction");
  assert.equal(rows[0].acceptedLinkStatus, "unlinked");
});

const benchmarkFalseInclusions = [
  ["req-1", 1, "Date of uploading of NIQ & other documents 08.05.2025 at 18.00 hrs"],
  ["req-3", 1, "Bid submission closing 28.05.2025 at 18:00 hrs"],
  ["req-5", 2, "Scanned copy of EMD. If any bidder is exempted from payment of EMD, relevant exemption document must be uploaded."],
  ["req-13", 2, "Character certificate undertaking that the vendor is not blacklisted by any government organization."],
  ["req-14", 2, "GST Registration Certificate and GST Clearance certificate."],
  ["req-34", 3, "An Earnest Money Deposit (EMD) for ₹200000 in the form of Bank Guarantee or Demand Draft or Fixed Deposit Receipt"],
  ["req-35", 3, "Offers received without Earnest Money or valid Certificate shall be summarily rejected."],
  ["req-36", 3, "EMD of unsuccessful bidder will be returned within one month of placement of Purchase Order."],
  ["req-37", 3, "In case of the successful bidder the EMD will be returned on receipt of the PBG."],
  ["req-38", 3, "Firms registered with DGS&D or NSIC must upload valid registration in place of EMD document."],
  ["req-39", 3, "Vendors have successfully executed two Purchase Orders in the last three Financial Years; copies must be uploaded in place of EMD."],
  ["req-40", 3, "The format for PBG shall be as per the format enclosed at Annexure V."],
  ["req-41", 3, "For foreign purchase, the local Agent shall submit the PBG; a foreign bank PBG shall be endorsed by its counterpart in India."],
  ["req-42", 3, "The PBG may be valid for warranty period + 2 months and submitted within 21 days from installation."],
  ["req-23", 3, "Quoted rates must be valid for 120 days from the last date of submission of quotation."],
  ["req-29", 3, "Dealers or Agents quoting on behalf of Manufacturer must upload a valid dealership certificate."],
  ["req-47", 3, "IIT may terminate the contract and forfeit the PBG for failure to comply with the guarantees above."],
  ["req-49", 3, "Slab 1: PO value ₹1.01–3.00 lakhs — PBG Rate: 3%"],
  ["req-50", 3, "Slab 2: PO value ₹3.00–5.00 lakhs — PBG Rate: 4%"],
  ["req-51", 3, "Slab 3: PO value ₹5.00 lakhs and more — PBG Rate: 5%"],
  ["req-185", 12, "EMD submitted (as applicable)"],
  ["req-186", 12, "Certificate of up-to-date Sales Tax clearance, GST Registration Certificate provided"],
  ["req-187", 12, "Payment term agreed"],
  ["req-188", 12, "Penalty clause for delay agreed"],
];

test("screens every flagged and adjacent administrative benchmark row when the model labels it requirement", () => {
  for (const [requirementId, page, sourceQuote] of benchmarkFalseInclusions) {
    const result = classifyCandidateScope("requirement", sourceQuote);
    assert.ok(["rejected", "retained_for_review"].includes(result.outcome), `${requirementId} p.${page}: ${sourceQuote}`);
    assert.ok(["instruction", "ambiguous"].includes(result.effectiveRowType), `${requirementId} p.${page}: ${sourceQuote}`);
    assert.ok(result.reason.length > 0, `${requirementId} p.${page}: missing disposition reason`);
  }
});

test("preserves page-11 service obligations when originally labeled requirement", () => {
  for (const sourceQuote of iitgServiceAnchorGroups) {
    const result = classifyCandidateScope("requirement", sourceQuote);
    assert.equal(result.outcome, "kept", sourceQuote);
    assert.equal(result.effectiveRowType, "requirement", sourceQuote);
    assert.equal(result.requiresHumanReview, false, sourceQuote);
  }
});

test("preserves technical values and source quote while accepting a technical requirement", () => {
  const sourceQuote = "The supplied laser shall have wavelength 532 nm ± 2 nm.";
  const result = classifyCandidateScope("requirement", sourceQuote);
  assert.equal(result.outcome, "kept");
  assert.equal(result.effectiveRowType, "requirement");
  assert.equal(sourceQuote, "The supplied laser shall have wavelength 532 nm ± 2 nm.");
});

test("keeps technical documentation as an obligation and sends admin-mixed wording to review", () => {
  const technicalDocument = classifyCandidateScope("requirement", "The supplier shall submit calibration certificates with each unit.");
  assert.equal(technicalDocument.outcome, "kept");
  assert.equal(technicalDocument.effectiveRowType, "requirement");

  const mixed = classifyCandidateScope("requirement", "The tender submission must include the bid form, and the supplier shall provide calibration certificates.");
  assert.equal(mixed.outcome, "retained_for_review");
  assert.equal(mixed.effectiveRowType, "ambiguous");
  assert.equal(mixed.requiresHumanReview, true);
});

test("reconciles administrative exclusions, review-only mixed clauses, and accepted source-grounded service rows", () => {
  const ledger = new CandidateTraceLedger("iitg-synthetic-fingerprint");
  const terminal = { accepted: [], rejected: [], discarded: [] };
  for (const [requirementId, page, sourceQuote] of benchmarkFalseInclusions) {
    const candidateId = ledger.register({ page, origin: "text_page_omission_audit", modelQuote: sourceQuote, sourceQuote, sourceQuoteStatus: "matched", sourceElementIds: [`page-${page}:fixture:${requirementId}`] });
    const decision = classifyCandidateScope("requirement", sourceQuote);
    ledger.recordClassification(candidateId, decision);
    if (decision.outcome === "rejected") {
      terminal.rejected.push(candidateId);
      ledger.terminate(candidateId, { disposition: "rejected", responsibleStage: "candidate_type_validation", rejectionCategory: decision.reason });
    } else {
      assert.equal(decision.outcome, "retained_for_review", requirementId);
      terminal.discarded.push(candidateId);
      ledger.terminate(candidateId, { disposition: "discarded", responsibleStage: "candidate_type_validation", rejectionCategory: "retained_for_human_classification_review" });
    }
  }

  for (const [index, sourceQuote] of iitgServiceAnchorGroups.entries()) {
    const candidateId = ledger.register({ page: 11, origin: "initial_extraction", modelQuote: sourceQuote, sourceQuote, sourceQuoteStatus: "matched", sourceElementIds: [`page-11:fixture:service-${index + 1}`] });
    const decision = classifyCandidateScope("requirement", sourceQuote);
    ledger.recordClassification(candidateId, decision);
    assert.equal(decision.outcome, "kept", sourceQuote);
    terminal.accepted.push(candidateId);
    ledger.terminate(candidateId, { disposition: "accepted", responsibleStage: "source_evidence_validation", finalRequirementId: `req-service-${index + 1}` });
  }

  assert.equal(terminal.rejected.length + terminal.discarded.length + terminal.accepted.length, benchmarkFalseInclusions.length + iitgServiceAnchorGroups.length);
  assert.deepEqual(ledger.summary(), { total: 27, accepted: 3, rejected: 23, duplicate: 0, merged: 0, discarded: 1, incomplete: 0 });
  assert.equal(ledger.records.filter((record) => record.disposition === "accepted").every((record) => record.finalRequirementId && record.classificationDecision?.effectiveRowType === "requirement"), true);
  assert.equal(ledger.records.every((record) => record.sourceQuoteStatus === "matched" && record.sourceElementIds.length === 1), true);
});
