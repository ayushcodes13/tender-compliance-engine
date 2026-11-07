import type { RequirementSourceReference } from "./source-document";

export type CandidateClassificationDecision = {
  originalRowType: string;
  effectiveRowType: "requirement" | "section" | "optional_heading" | "instruction" | "header" | "ambiguous";
  outcome: "kept" | "reclassified_for_review" | "retained_for_review" | "rejected";
  reason: string;
  requiresHumanReview: boolean;
};

export type ClassificationReviewCandidate = {
  candidateId?: string;
  page: number;
  quote: string;
  originalClassification: string;
  effectiveClassification: string;
  reason: string;
  sourceReference: RequirementSourceReference;
};

const normalize = (value: string) => value.replace(/\s+/g, " ").trim().toLowerCase();

const ADMINISTRATIVE_PATTERNS: Array<[RegExp, string]> = [
  [/\b(?:emd|earnest money(?: deposit)?|bid security|tender fee)\b/, "bid_security_or_tender_fee"],
  [/\b(?:bank guarantee|performance bank guarantee|\bpbg\b|performance security|security deposit)\b/, "financial_security_term"],
  [/\b(?:payment terms?|payment schedule|advance payment|invoice|billing)\b|\b(?:gst|sales tax|tax clearance)\b.{0,60}\b(?:certificate|registration|clearance|deduction|number)\b/, "payment_or_tax_term"],
  [/\b(?:commercial bid|financial bid|price bid|quoted price|cost escalation|pricing|price schedule)\b/, "commercial_price_term"],
  [/\b(?:delivery schedule|delivery period|liquidated damages|penalt(?:y|ies)|turnover|eligibility|bid validity)\b/, "procurement_or_eligibility_term"],
  [/\b(?:date of uploading|bid submission|tender submission|submission closing|last date of submission|bidder shall fill|must be filled by the bidder|indicate compliance|compliance status|technical compliance report|tender document)\b/, "bid_submission_or_form_instruction"],
  [/\b(?:blacklisted|not blacklisted|character certificate|past performance|previously executed|purchase orders in the last|registered with (?:dgs&d|nsic)|dealer(?:ship)? certificate|vendor registration|gst registration certificate)\b/, "vendor_qualification_or_registration"],
  [/\b(?:notice inviting tender|tender is hereby invited|purchaser reserves the right|tender may be cancelled|contact the procurement office)\b/, "administrative_notice"],
];

const SERVICE_OBLIGATION_PATTERNS: Array<[RegExp, string]> = [
  [/(?:annual maintenance contract|\bamc\b).{0,90}(?:five|5)[ -]year|(?:five|5)[ -]year.{0,90}(?:annual maintenance contract|\bamc\b)/, "duration_bound_maintenance_contract"],
  [/(?:service visits?).{0,100}(?:calibration|maintenance)|(?:calibration|maintenance).{0,100}(?:service visits?)/, "recurring_service_and_calibration"],
  [/(?:local office|authorized associate|authorised associate).{0,100}\bindia\b|\bindia\b.{0,100}(?:local office|authorized associate|authorised associate)/, "local_after_sales_presence"],
  [/(?:after[ -]sales|service support).{0,100}(?:support|maintenance|timely)|(?:timely|maintenance).{0,100}(?:after[ -]sales|service support)/, "after_sales_support_commitment"],
  [/spare parts?.{0,140}(?:minimum|five|5|warranty|years?)|(?:minimum|five|5|warranty|years?).{0,140}spare parts?/, "time_bound_spare_parts_support"],
  [/(?:supplier|vendor|contractor|oem).{0,100}(?:shall|must|will|is required to).{0,100}(?:submit|provide|furnish|supply).{0,100}(?:calibration|maintenance|operation|service).{0,100}(?:certificate|manual|instruction|record)|(?:calibration|maintenance|operation|service).{0,100}(?:certificate|manual|instruction|record).{0,100}(?:submit|provide|furnish|supply)/, "supplier_technical_document_submission"],
  [/(?:technical|product|equipment)\s+(?:leaflet|literature|catalogue|catalog|datasheet|manual|certificate|documentation).{0,100}(?:provide|submit|furnish|supply|include|accompany|upload|certificate|required)|(?:provide|submit|furnish|supply|include|accompany|upload).{0,100}(?:technical|product|equipment)\s+(?:leaflet|literature|catalogue|catalog|datasheet|manual|certificate|documentation)/, "technical_documentation_fulfillment"],
];

const TECHNICAL_SCOPE_PATTERNS: RegExp[] = [
  /\b(?:technical|specification|parameter|equipment|instrument|product|device|system|laser|pump|microscope|spectrometer|optical|electrical|mechanical|environmental|material|standard|test|measurement|accuracy|resolution|precision|repeatability|reproducibility|wavelength|voltage|current|power|frequency|dimension|capacity|range|tolerance|pressure|temperature|humidity|aperture|load|travel|noise|vacuum|interface|controller|motor|calibration|warranty|maintenance|installation|commissioning|training|acceptance)\b/,
  /(?:≤|≥|±|<=|>=|\b\d+(?:\.\d+)?\s*(?:mm|cm|m|µm|um|nm|μm|kg|g|mg|l|ml|v|kv|mv|a|ma|w|kw|mw|hz|khz|mhz|ghz|bar|mbar|pa|kpa|°c|db|dbm|rpm|degrees?|%))\b/i,
];

/**
 * Screens every proposed row for out-of-scope procurement mechanics, including
 * rows the model labels as requirements. Supplier fulfillment can remain in
 * scope; unresolved and mixed clauses stay review-only. Source quote
 * validation still runs later for candidates admitted to the matrix.
 */
export function classifyCandidateScope(rowType: string | undefined, sourceQuote: string): CandidateClassificationDecision {
  const originalRowType = rowType ?? "unclassified";
  if (originalRowType === "header") {
    return { originalRowType, effectiveRowType: "header", outcome: "rejected", reason: "document_navigation_or_table_header", requiresHumanReview: false };
  }
  if (originalRowType === "section" || originalRowType === "optional_heading") {
    return { originalRowType, effectiveRowType: originalRowType, outcome: "kept", reason: "structural_heading_preserved", requiresHumanReview: false };
  }

  const text = normalize(sourceQuote);
  const administrativeMatches = ADMINISTRATIVE_PATTERNS.filter(([pattern]) => pattern.test(text));
  const serviceMatches = SERVICE_OBLIGATION_PATTERNS.filter(([pattern]) => pattern.test(text));
  const administrativeReasons = administrativeMatches.map(([, reason]) => reason);
  const serviceReasons = serviceMatches.map(([, reason]) => reason);
  const hasSupplierPerformanceFrame = /\b(?:supplier|vendor|contractor|manufacturer|oem)\b.{0,100}\b(?:shall|must|will|is required to|is responsible for|undertakes? to)\b|\b(?:shall|must|will|is required to|is responsible for|undertakes? to)\b.{0,100}\b(?:supplier|vendor|contractor|manufacturer|oem)\b/.test(text);
  const hasTechnicalScope = serviceMatches.length > 0 || TECHNICAL_SCOPE_PATTERNS.some((pattern) => pattern.test(text));
  const hasConcreteTechnicalContent = serviceMatches.length > 0
    || /\b(?:warranty period|calibration|maintenance|installation|commissioning|training|acceptance test|spare parts|accuracy|resolution|wavelength|voltage|frequency|dimension|capacity|tolerance|pressure|temperature|humidity|aperture|travel|vacuum|astm|iso|iec)\b/.test(text)
    || /(?:≤|≥|±|<=|>=|\b\d+(?:\.\d+)?\s*(?:mm|cm|m|µm|um|nm|μm|kg|g|mg|l|ml|v|kv|mv|a|ma|w|kw|mw|hz|khz|mhz|ghz|bar|mbar|pa|kpa|°c|db|dbm|rpm|degrees?)\b)/i.test(text);

  if (administrativeMatches.length > 0 && (serviceMatches.length > 0 || hasSupplierPerformanceFrame && hasTechnicalScope || hasConcreteTechnicalContent)) {
    return { originalRowType, effectiveRowType: "ambiguous", outcome: "retained_for_review", reason: "mixed_administrative_and_supplier_obligation", requiresHumanReview: true };
  }

  if (administrativeMatches.length > 0) {
    return { originalRowType, effectiveRowType: "instruction", outcome: "rejected", reason: administrativeReasons[0], requiresHumanReview: false };
  }

  if (serviceMatches.length > 0) {
    if (originalRowType === "instruction" || originalRowType === "ambiguous" || !hasSupplierPerformanceFrame && serviceReasons.includes("technical_documentation_fulfillment")) {
      return { originalRowType, effectiveRowType: "requirement", outcome: "reclassified_for_review", reason: serviceReasons[0], requiresHumanReview: true };
    }
    return { originalRowType, effectiveRowType: "requirement", outcome: "kept", reason: serviceReasons[0], requiresHumanReview: false };
  }

  if (hasTechnicalScope) {
    if (originalRowType === "instruction" || originalRowType === "ambiguous" || originalRowType === "unclassified") {
      if (hasSupplierPerformanceFrame && TECHNICAL_SCOPE_PATTERNS.some((pattern) => pattern.test(text))) {
        return { originalRowType, effectiveRowType: "requirement", outcome: "reclassified_for_review", reason: serviceReasons[0] ?? "source_grounded_technical_scope", requiresHumanReview: true };
      }
      return { originalRowType, effectiveRowType: "ambiguous", outcome: "retained_for_review", reason: "unresolved_instruction_classification", requiresHumanReview: true };
    }
    return { originalRowType, effectiveRowType: "requirement", outcome: "kept", reason: "source_grounded_technical_scope", requiresHumanReview: false };
  }

  if (originalRowType === "requirement") {
    return { originalRowType, effectiveRowType: "requirement", outcome: "kept", reason: "no_administrative_scope_conflict", requiresHumanReview: false };
  }
  if (originalRowType === "instruction" || originalRowType === "ambiguous" || originalRowType === "unclassified") {
    return { originalRowType, effectiveRowType: "ambiguous", outcome: "retained_for_review", reason: originalRowType === "ambiguous" ? "unresolved_source_structure" : "unresolved_instruction_classification", requiresHumanReview: true };
  }
  return { originalRowType, effectiveRowType: "ambiguous", outcome: "retained_for_review", reason: "unresolved_candidate_scope", requiresHumanReview: true };
}

/** @deprecated Use classifyCandidateScope for all extracted candidate types. */
export const classifyInstructionCandidate = classifyCandidateScope;
