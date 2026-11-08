import test from "node:test";
import assert from "node:assert/strict";
import { applyValidatedSourceObligationGroup, canJoinValidatedSourceObligationGroup, classifyCandidateScope } from "./candidate-classification.ts";
import { CandidateTraceLedger } from "./candidate-trace.ts";
import { collectSourceTableCoverageRows } from "./coverage-ledger.ts";

const iitgServiceAnchorGroups = [
  "a separate charge for a Five-year Annual Maintenance Contract (AMC); Service visits; Yearly calibration; Routine maintenance services",
  "a local office or an authorized associate in India for timely after-sales support and maintenance",
  "availability of spare parts for a minimum period of five years beyond the initial warranty period",
];

const newlyObservedAdministrativeCases = [
  ["req-6", 2, "iv. PAN Detail and TIN number"],
  ["req-7", 2, "v. Registration Certificate"],
  ["req-8", 2, "vi. Banker’s Detail"],
  ["req-9", 2, "vii. List of reputed organizations/institutions, particularly to IIT/Institutes and other Government Organization where similar orders have been executed, if any (copy (s) of the Purchase Orders and Installation certificates will have to be uploaded)."],
  ["req-21", 3, "(a) The Purchase Order (PO) shall be executed as per terms and conditions mentioned therein."],
  ["req-25", 3, "(e) The guarantee is to the extent of the below mentioned slab."],
  ["req-26", 4, "Maximum within 45 days from the date of issue of purchase order in case of indigenous items and 90 days for imported items."],
  ["req-28", 4, "All aspects of safe delivery shall be the exclusive responsibility of the vendor."],
  ["req-29", 4, "At the destination site, the package will be opened only in the presence of IIT user/representative and vendor's representative."],
  ["req-31", 4, "Part delivery is not allowed."],
  ["req-32", 4, "The date of delivery should be strictly adhered to otherwise the Director, IITG reserves the right not to accept delivery in part or full."],
  ["req-33", 4, "HSN/SAC No of the items must be clearly mentioned in the quotation along with GST No."],
];

const mixedSourceCases = [
  ["req-3", "vi. HSN/SAC Number, ISO/ISI Certificate and Proof of Certification as per specification"],
  ["req-5", "i. Bidder’s detail and its Service Centre detail as per format at Annexure - III"],
  ["req-15", "The bidders should clearly state the detail address, contact number and email ids of after sales service centre in India in Bidder’s Details under Statutory Cover as at Annexure - III"],
];

const page11ServiceRequirements = [
  "The quote must include a separate charge for a Five - year Annual Maintenance Contract (AMC), covering: Service visits; Yearly calibration; Routine maintenance services, and Provision of spare parts and necessary consumables",
  "The supplier must have a local office or an authorized associate in India to ensure timely after - sales support and maintenance.",
  "An undertaking must be provided for: After - sales service and availability of spare parts for a minimum period of five years beyond the initial warranty period.",
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
    ["requirement", "The format for PBG shall be as per the format enclosed at Annexure V."],
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

test("preserves source-grounded equipment and supplier obligations across unfamiliar wording", () => {
  const positiveCases = [
    "Cryostat shall retain helium for 90 days.",
    "Firmware must support the OPC UA protocol.",
    "Ferromagnetic stainless steel.",
    "At least two USB ports should be provided with the instrument.",
    "The fixture must allow the machine to use the full range of specimen grips.",
    "The setup shall comply with ASTM D4595.",
    "The jaw faces shall align with their corresponding opposing surfaces.",
    "The supplier shall rectify or replace defects during the guarantee period.",
    "An emergency stop button shall be within easy reach of the operator.",
    "The PC must include a 512 GB solid-state drive and 16 GB memory.",
    "The software shall import test results in CSV and PDF formats.",
    "The supplier shall deliver the equipment within 45 days of the purchase order.",
  ];
  for (const quote of positiveCases) {
    const result = classifyCandidateScope("requirement", quote);
    assert.ok(["kept", "reclassified_for_review"].includes(result.outcome), quote);
    assert.equal(result.effectiveRowType, "requirement", quote);
  }
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

test("holds source-verified mixed bidder, tax, service-centre, and technical-document clauses for review", () => {
  for (const [requirementId, quote] of mixedSourceCases) {
    const result = classifyCandidateScope("requirement", quote);
    assert.equal(result.outcome, "retained_for_review", requirementId);
    assert.equal(result.effectiveRowType, "ambiguous", requirementId);
    assert.equal(result.requiresHumanReview, true, requirementId);
    assert.ok(result.reason.length > 0, requirementId);
  }
});

test("screens the twelve newly observed administrative rows without overgeneralizing incidental technical words", () => {
  for (const [requirementId, page, quote] of newlyObservedAdministrativeCases) {
    const result = classifyCandidateScope("requirement", quote);
    const expected = ["req-26", "req-28", "req-32"].includes(requirementId) ? "retained_for_review" : "rejected";
    assert.equal(result.outcome, expected, `${requirementId} p.${page}`);
    assert.ok(result.reason.length > 0, `${requirementId} p.${page}`);
    assert.notEqual(result.effectiveRowType, "requirement", `${requirementId} p.${page}`);
  }
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
    assert.equal(canJoinValidatedSourceObligationGroup(result), false, `${requirementId} p.${page}: source grouping must not promote this administrative case`);
  }
});

test("preserves the three exact page-11 service obligations with their recorded model labels", () => {
  for (const [sourceQuote, rowType, expectedOutcome] of [
    [page11ServiceRequirements[0], "instruction", "reclassified_for_review"],
    [page11ServiceRequirements[1], "requirement", "kept"],
    [page11ServiceRequirements[2], "requirement", "kept"],
  ]) {
    const result = classifyCandidateScope(rowType, sourceQuote);
    assert.equal(result.outcome, expectedOutcome, sourceQuote);
    assert.equal(result.effectiveRowType, "requirement", sourceQuote);
    assert.equal(result.requiresHumanReview, expectedOutcome !== "kept", sourceQuote);
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

  const productLiterature = classifyCandidateScope("requirement", "The model and specifications quoted should be highlighted in the product literature.");
  assert.equal(productLiterature.effectiveRowType, "requirement");
  assert.equal(productLiterature.requiresHumanReview, true);

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
  const summary = ledger.summary();
  assert.equal(summary.total, benchmarkFalseInclusions.length + iitgServiceAnchorGroups.length);
  assert.equal(summary.accepted, terminal.accepted.length);
  assert.equal(summary.rejected, terminal.rejected.length);
  assert.equal(summary.discarded, terminal.discarded.length);
  assert.equal(summary.accepted + summary.rejected + summary.duplicate + summary.merged + summary.discarded + summary.incomplete, summary.total);
  assert.equal(ledger.records.filter((record) => record.disposition === "accepted").every((record) => record.finalRequirementId && record.classificationDecision?.effectiveRowType === "requirement"), true);
  assert.equal(ledger.records.every((record) => record.sourceQuoteStatus === "matched" && record.sourceElementIds.length === 1), true);
});


test("keeps bidder-form acknowledgement fields out of the accepted technical matrix", () => {
  const formFields = [
    "Warranty period agreed",
    "After-sales service terms agreed",
    "After-sales terms agreed and contact details supplied",
    "Service Centre Guwahati: Contact person, phone, e-mail and address",
    "Guwahati Service Centre Address and Contact Details",
    "The bidder must provide the service centre contact number and email address in the form.",
  ];
  for (const quote of formFields) {
    const decision = classifyCandidateScope("requirement", quote);
    assert.equal(decision.outcome, "retained_for_review", quote);
    assert.equal(decision.effectiveRowType, "ambiguous", quote);
    assert.equal(decision.requiresHumanReview, true, quote);
    assert.notEqual(decision.reason, "no_administrative_scope_conflict", quote);
  }
});

test("preserves substantive maintenance and local-service promises while screening contact forms", () => {
  const obligations = [
    "The supplier must have a local office or an authorized associate in India to ensure timely after-sales support and maintenance.",
    "The supplier shall provide five years of warranty support with routine maintenance services.",
    "The quote must include a separate charge for a Five - year Annual Maintenance Contract (AMC), covering: Service visits; Yearly calibration; Routine maintenance services, and Provision of spare parts and necessary consumables",
    "An undertaking must be provided for after-sales service and availability of spare parts for five years beyond warranty.",
  ];
  for (const quote of obligations) {
    const decision = classifyCandidateScope("requirement", quote);
    assert.equal(decision.effectiveRowType, "requirement", quote);
    assert.notEqual(decision.outcome, "rejected", quote);
    assert.notEqual(decision.outcome, "retained_for_review", quote);
  }
});

test("holds a mixed performance commitment and service contact disclosure for human scope review", () => {
  const sourceQuote = "The supplier shall operate a local service centre for five years and submit its contact person, telephone and e-mail details.";
  const decision = classifyCandidateScope("requirement", sourceQuote);
  assert.equal(decision.outcome, "retained_for_review");
  assert.equal(decision.effectiveRowType, "ambiguous");
  assert.equal(decision.requiresHumanReview, true);
});

test("records a validated source-list parent/member relationship without changing the source classification", () => {
  const parent = classifyCandidateScope("instruction", "The quote must include a separate charge for a Five - year Annual Maintenance Contract (AMC), covering:");
  assert.equal(parent.outcome, "retained_for_review");
  const parentId = "cand-amc-parent";
  const group = { id: "sog-doc-p11-o4", role: "parent", parentCandidateId: parentId };
  const retained = applyValidatedSourceObligationGroup(parent, group);
  assert.equal(retained.originalRowType, "instruction");
  assert.equal(retained.effectiveRowType, "requirement");
  assert.equal(retained.outcome, "kept");
  assert.equal(retained.reason, "validated_source_obligation_group_parent");
  assert.equal(retained.requiresHumanReview, true, "grouping cannot silently clear earlier scope review");
  assert.equal(retained.sourceObligationGroupId, group.id);
  assert.equal(retained.sourceObligationGroupRole, "parent");

  const child = classifyCandidateScope("requirement", "Provision of spare parts and necessary consumables");
  assert.equal(child.outcome, "retained_for_review");
  const member = applyValidatedSourceObligationGroup(child, { ...group, role: "member" });
  assert.equal(member.originalRowType, "requirement");
  assert.equal(member.effectiveRowType, "requirement");
  assert.equal(member.outcome, "kept");
  assert.equal(member.reason, "validated_source_obligation_group_member");
  assert.equal(member.sourceObligationGroupId, group.id);
  assert.equal(member.sourceObligationGroupParentCandidateId, parentId);
  assert.equal(member.requiresHumanReview, true, "parent context does not independently adjudicate a fragment");
});

test("does not let source grouping override administrative or mixed-form scope decisions", () => {
  const excludedOrReviewOnly = [
    ["instruction", "EMD of ₹50,000 must be submitted with the bid."],
    ["requirement", "Payment shall be released within 30 days of invoice."],
    ["instruction", "The bidder shall provide a bank guarantee with the tender."],
    ["instruction", "The tender submission must include the bid form, and the supplier shall provide calibration certificates."],
    ["requirement", "Warranty period agreed"],
    ["requirement", "Service Centre details: Contact person, telephone and e-mail"],
  ];
  for (const [rowType, quote] of excludedOrReviewOnly) {
    const decision = classifyCandidateScope(rowType, quote);
    assert.equal(canJoinValidatedSourceObligationGroup(decision), false, quote);
  }

  const parent = classifyCandidateScope("instruction", "The quote must include a separate charge for a Five - year Annual Maintenance Contract (AMC), covering:");
  const member = classifyCandidateScope("requirement", "Service visits;");
  assert.equal(canJoinValidatedSourceObligationGroup(parent), true);
  assert.equal(canJoinValidatedSourceObligationGroup(member), true);
});

test("retains NIOT instrument hardware deliverables while excluding pure commercial/logistics clauses", () => {
  // P0 Missing technical requirements
  const displayDecision = classifyCandidateScope("requirement", "Display: Digital readout");
  assert.equal(displayDecision.outcome, "kept");
  assert.equal(displayDecision.effectiveRowType, "requirement");
  assert.equal(displayDecision.reason, "source_grounded_technical_scope");

  const readoutDecision = classifyCandidateScope("requirement", "Digital readout");
  assert.equal(readoutDecision.outcome, "kept");
  assert.equal(readoutDecision.effectiveRowType, "requirement");

  const packingCaseDecision = classifyCandidateScope("requirement", "Autosal packing case for Auatosal 8400B-1 No.");
  assert.equal(packingCaseDecision.outcome, "kept");
  assert.equal(packingCaseDecision.effectiveRowType, "requirement");

  // P0 Administrative contamination: Pure commercial/logistics clauses must be rejected
  const orderAcceptance = classifyCandidateScope("instruction", "The OEM should accept the Order acceptance within 7 days from the date of receipt of PO , failing which it shall be presumed that the bidder is not interested, and");
  assert.equal(orderAcceptance.outcome, "rejected");
  assert.equal(orderAcceptance.effectiveRowType, "instruction");
  assert.equal(orderAcceptance.reason, "order_acceptance_or_po_receipt");

  const dapInsurance = classifyCandidateScope("requirement", "Insurance should be arranged from SHIPPERS WAREHOUSE TO CONSIGNEE’S WAREHOUSE up to installation and commissioning... for DAP value plus 10%...");
  assert.equal(dapInsurance.outcome, "rejected");
  assert.equal(dapInsurance.effectiveRowType, "instruction");
  assert.equal(dapInsurance.reason, "insurance_or_transit_logistics");

  const seaWorthyPacking = classifyCandidateScope("requirement", "Sufficient care should be taken on packing and it should be sea worthy packing as per International standard.");
  assert.equal(seaWorthyPacking.outcome, "rejected");
  assert.equal(seaWorthyPacking.effectiveRowType, "instruction");
  assert.equal(seaWorthyPacking.reason, "cargo_packaging_logistics");

  const wireTransferTpi = classifyCandidateScope("requirement", "The Third Party Inspection is not mandatory for Indian bidders and payment made after acceptance at sight through Wire Transfer...");
  assert.equal(wireTransferTpi.outcome, "rejected");
  assert.equal(wireTransferTpi.effectiveRowType, "instruction");
  assert.equal(wireTransferTpi.reason, "payment_method_or_inspection_administration");

  const woodPackaging = classifyCandidateScope("requirement", "If Seller uses wood packaging materials such as pallets, crates, boxes, dunnages, cases, skids and ply wood, it shall be heat treated or fumigated with methyl bromide as per ISPM 15 standards and packing should contain phytosanitary certificate.");
  assert.equal(woodPackaging.outcome, "rejected");
  assert.equal(woodPackaging.effectiveRowType, "instruction");
  assert.equal(woodPackaging.reason, "wood_packaging_or_phytosanitary_logistics");

  const itemCommentary = classifyCandidateScope("requirement", "An item-by- item commentary on the Purchaser’s Technical Specifications demonstrating substantial responsiveness");
  assert.equal(itemCommentary.outcome, "rejected");
  assert.equal(itemCommentary.effectiveRowType, "instruction");

  const bidderSubstitution = classifyCandidateScope("requirement", "The Bidder may substitute these in its bid, provided that it demonstrates to the Purchaser’s satisfaction");
  assert.equal(bidderSubstitution.outcome, "rejected");
  assert.equal(bidderSubstitution.effectiveRowType, "instruction");

  // Mixed bidder submission requirement retained for review
  const mixedSubmission = classifyCandidateScope("requirement", "Wherever the submission of documentary evidence (as proof of some parameter) is mentioned in the SCC, the same shall be enclosed in the quotation.");
  assert.equal(mixedSubmission.outcome, "retained_for_review");
  assert.equal(mixedSubmission.effectiveRowType, "ambiguous");
  assert.equal(mixedSubmission.reason, "mixed_administrative_and_supplier_obligation");

  // Genuine technical obligations must not be suppressed
  const warranty = classifyCandidateScope("requirement", "This warranty should be minimum for the period of 12 months from the date of installation.");
  assert.equal(warranty.outcome, "kept");
  assert.equal(warranty.effectiveRowType, "requirement");

  const training = classifyCandidateScope("requirement", "Operational training to be provided at NIOT at the time of installation and commissioning.");
  assert.equal(training.outcome, "kept");
  assert.equal(training.effectiveRowType, "requirement");

  const installObligation = classifyCandidateScope("requirement", "The supplier shall install and commission the Autosal at NIOT.");
  assert.equal(installObligation.outcome, "kept");
  assert.equal(installObligation.effectiveRowType, "requirement");
});
