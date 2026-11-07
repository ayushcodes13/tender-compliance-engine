export type CandidateClassificationDecision = {
  originalRowType: string;
  effectiveRowType: "requirement" | "section" | "optional_heading" | "instruction" | "header" | "ambiguous";
  outcome: "kept" | "reclassified_for_review" | "retained_for_review" | "rejected";
  reason: string;
  requiresHumanReview: boolean;
};

const normalize = (value: string) => value.replace(/\s+/g, " ").trim().toLowerCase();

const ADMINISTRATIVE_PATTERNS: Array<[RegExp, string]> = [
  [/\b(?:emd|earnest money deposit|bid security|tender fee)\b/, "bid_security_or_tender_fee"],
  [/\b(?:bank guarantee|performance security|security deposit)\b/, "financial_security_term"],
  [/\b(?:payment terms?|payment schedule|advance payment|invoice|billing|gst|taxes?)\b/, "payment_or_tax_term"],
  [/\b(?:commercial bid|financial bid|price bid|quoted price|cost escalation|pricing|price schedule)\b/, "commercial_price_term"],
  [/\b(?:delivery schedule|delivery period|liquidated damages|penalt(?:y|ies)|turnover|eligibility|bid validity)\b/, "procurement_or_eligibility_term"],
  [/\b(?:submit|submission|submitted|bidder shall fill|must be filled by the bidder|indicate compliance|compliance status|technical compliance report|catalogue|tender document)\b/, "bid_submission_or_form_instruction"],
  [/\b(?:notice inviting tender|tender is hereby invited|purchaser reserves the right|tender may be cancelled|contact the procurement office)\b/, "administrative_notice"],
];

const SERVICE_OBLIGATION_PATTERNS: Array<[RegExp, string]> = [
  [/(?:annual maintenance contract|\bamc\b).{0,90}(?:five|5)[ -]year|(?:five|5)[ -]year.{0,90}(?:annual maintenance contract|\bamc\b)/, "duration_bound_maintenance_contract"],
  [/(?:service visits?).{0,100}(?:calibration|maintenance)|(?:calibration|maintenance).{0,100}(?:service visits?)/, "recurring_service_and_calibration"],
  [/(?:local office|authorized associate|authorised associate).{0,100}\bindia\b|\bindia\b.{0,100}(?:local office|authorized associate|authorised associate)/, "local_after_sales_presence"],
  [/(?:after[ -]sales|service support).{0,100}(?:support|maintenance|timely)|(?:timely|maintenance).{0,100}(?:after[ -]sales|service support)/, "after_sales_support_commitment"],
  [/spare parts?.{0,140}(?:minimum|five|5|warranty|years?)|(?:minimum|five|5|warranty|years?).{0,140}spare parts?/, "time_bound_spare_parts_support"],
];

/**
 * Reconciles a model's broad "instruction" label with the source meaning. Only
 * explicit procurement mechanics are discarded. Recognized supplier service
 * commitments are retained as unchecked requirements, and unresolved cases
 * remain visible for human review. Source quote validation still runs later.
 */
export function classifyInstructionCandidate(rowType: string | undefined, sourceQuote: string): CandidateClassificationDecision {
  const originalRowType = rowType ?? "unclassified";
  if (originalRowType !== "instruction" && originalRowType !== "ambiguous" && originalRowType !== "header") {
    return { originalRowType, effectiveRowType: originalRowType as CandidateClassificationDecision["effectiveRowType"], outcome: "kept", reason: "model_classified_as_non_instruction", requiresHumanReview: false };
  }

  if (originalRowType === "header") {
    return { originalRowType, effectiveRowType: "header", outcome: "rejected", reason: "document_navigation_or_table_header", requiresHumanReview: false };
  }

  const text = normalize(sourceQuote);
  for (const [pattern, reason] of ADMINISTRATIVE_PATTERNS) {
    if (pattern.test(text)) {
      return { originalRowType, effectiveRowType: "instruction", outcome: "rejected", reason, requiresHumanReview: false };
    }
  }

  for (const [pattern, reason] of SERVICE_OBLIGATION_PATTERNS) {
    if (pattern.test(text)) {
      return { originalRowType, effectiveRowType: "requirement", outcome: "reclassified_for_review", reason, requiresHumanReview: true };
    }
  }

  return originalRowType === "ambiguous"
    ? { originalRowType, effectiveRowType: "ambiguous", outcome: "retained_for_review", reason: "unresolved_source_structure", requiresHumanReview: true }
    : { originalRowType, effectiveRowType: "requirement", outcome: "retained_for_review", reason: "unresolved_instruction_classification", requiresHumanReview: true };
}
