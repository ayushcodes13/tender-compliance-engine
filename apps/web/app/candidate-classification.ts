import type { RequirementSourceReference } from "./source-document";

export type CandidateClassificationDecision = {
  originalRowType: string;
  effectiveRowType: "requirement" | "section" | "optional_heading" | "instruction" | "header" | "ambiguous";
  outcome: "kept" | "reclassified_for_review" | "retained_for_review" | "rejected";
  reason: string;
  requiresHumanReview: boolean;
  sourceObligationGroupId?: string;
  sourceObligationGroupRole?: "parent" | "member";
  sourceObligationGroupParentCandidateId?: string;
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

const SOURCE_GROUP_BLOCKED_REVIEW_REASONS = new Set([
  "form_agreement_not_supplier_obligation",
  "service_contact_form_requires_scope_review",
  "mixed_administrative_and_supplier_obligation",
]);

export function canJoinValidatedSourceObligationGroup(decision: CandidateClassificationDecision): boolean {
  return decision.outcome !== "rejected" && !SOURCE_GROUP_BLOCKED_REVIEW_REASONS.has(decision.reason);
}

export function applyValidatedSourceObligationGroup(
  decision: CandidateClassificationDecision,
  group: { id: string; role: "parent" | "member"; parentCandidateId: string },
): CandidateClassificationDecision {
  return {
    ...decision,
    effectiveRowType: "requirement",
    outcome: "kept",
    reason: decision.outcome === "kept" ? decision.reason : `validated_source_obligation_group_${group.role}`,
    requiresHumanReview: false,
    sourceObligationGroupId: group.id,
    sourceObligationGroupRole: group.role,
    sourceObligationGroupParentCandidateId: group.parentCandidateId,
  };
}

const normalize = (value: string) => value.replace(/\s+/g, " ").trim().toLowerCase();

const ADMINISTRATIVE_PATTERNS: Array<[RegExp, string]> = [
  [/\b(?:emd|earnest money(?: deposit)?|bid security|tender fee)\b/, "bid_security_or_tender_fee"],
  [/\b(?:bank guarantee|performance bank guarantee|\bpbg\b|performance security|security deposit)\b|\bguarantee\b.{0,50}\b(?:slab|percentage|amount)\b/, "financial_security_term"],
  [/\b(?:payment terms?|payment schedule|advance payment|invoice|billing)\b|\b(?:gst|sales tax|tax clearance|hsn\s*\/\s*sac|sac\s*\/\s*hsn)\b.{0,100}\b(?:certificate|registration|clearance|deduction|number|no\.?|quotation|quote|invoice)?\b|\b(?:pan|tin)(?:\s+(?:card|detail|details|number|no\.?))?\b|\bbanker[’']?s?\s+details?\b/, "payment_tax_or_bidder_finance_detail"],
  [/\b(?:commercial bid|financial bid|price bid|quoted price|cost escalation|pricing|price schedule)\b/, "commercial_price_term"],
  [/\b(?:delivery schedule|delivery period|delivery time|delivery date|part delivery|safe delivery|liquidated damages|penalt(?:y|ies)|turnover|eligibility|bid validity)\b|\bpackage\b.{0,80}\b(?:opened|opening)\b.{0,80}\b(?:presence|representative)\b|\bdate of delivery\b.{0,100}\b(?:reserves? the right|not to accept)\b/, "procurement_or_logistics_term"],
  [/\b(?:date of uploading|bid submission|tender submission|submission closing|last date of submission|bidder shall fill|must be filled by the bidder|indicate compliance|compliance status|technical compliance report|tender document|statutory cover|bidder[’']?s? details?|format at annexure)\b/, "bid_submission_or_form_instruction"],
  [/\b(?:blacklisted|not blacklisted|character certificate|past performance|previously executed|prior experience|similar orders?|orders? have been executed|purchase orders? in the last|registered with (?:dgs&d|nsic)|dealer(?:ship)? certificate|vendor registration|registration certificate|gst registration certificate|list of reputed organizations?)\b/, "vendor_qualification_or_registration"],
  [/\b(?:purchase order|\bpo\b)\b.{0,80}\b(?:terms? and conditions?|shall be executed|mentioned therein)\b/, "purchase_order_contract_term"],
  [/\b(?:notice inviting tender|tender is hereby invited|purchaser reserves the right|tender may be cancelled|contact the procurement office)\b/, "administrative_notice"],
];

const SERVICE_OBLIGATION_PATTERNS: Array<[RegExp, string]> = [
  [/(?:annual maintenance contract|\bamc\b).{0,90}(?:five|5)[ -]year|(?:five|5)[ -]year.{0,90}(?:annual maintenance contract|\bamc\b)/, "duration_bound_maintenance_contract"],
  [/(?:service visits?).{0,100}(?:calibration|maintenance)|(?:calibration|maintenance).{0,100}(?:service visits?)/, "recurring_service_and_calibration"],
  [/(?:local office|authorized associate|authorised associate).{0,100}\bindia\b|\bindia\b.{0,100}(?:local office|authorized associate|authorised associate)/, "local_after_sales_presence"],
  [/(?:after[ -]sales|service support).{0,100}(?:support|maintenance|timely)|(?:timely|maintenance).{0,100}(?:after[ -]sales|service support)/, "after_sales_support_commitment"],
  [/spare parts?.{0,140}(?:minimum|five|5|warranty|years?)|(?:minimum|five|5|warranty|years?).{0,140}spare parts?/, "time_bound_spare_parts_support"],
  [/(?:supplier|vendor|contractor|oem).{0,100}(?:shall|must|will|is required to).{0,100}(?:submit|provide|furnish|supply).{0,100}(?:calibration|maintenance|operation|service).{0,100}(?:certificate|manual|instruction|record)|(?:calibration|maintenance|operation|service).{0,100}(?:certificate|manual|instruction|record).{0,100}(?:submit|provide|furnish|supply)/, "supplier_technical_document_submission"],
  [/(?:functional )?demonstrations?.{0,100}(?:service visits?|maintenance|commissioning)|(?:service visits?|maintenance|commissioning).{0,100}(?:functional )?demonstrations?/, "supplier_performance_demonstration"],
  [/(?:technical|product|equipment)\s+(?:leaflet|literature|catalogue|catalog|datasheet|manual|certificate|documentation).{0,100}(?:provide|submit|furnish|supply|include|accompany|upload|certificate|required)|(?:provide|submit|furnish|supply|include|accompany|upload).{0,100}(?:technical|product|equipment)\s+(?:leaflet|literature|catalogue|catalog|datasheet|manual|certificate|documentation)/, "technical_documentation_fulfillment"],
  [/(?:model|product|quoted)\s+and\s+(?:technical\s+)?specifications?.{0,100}\b(?:leaflet|literature|catalogue|catalog|datasheet)\b|\b(?:leaflet|literature|catalogue|catalog|datasheet)\b.{0,100}\b(?:model|product|quoted)\s+and\s+(?:technical\s+)?specifications?\b/, "technical_documentation_fulfillment"],
  [/\b(?:operation|operating|maintenance|user|service)\s+(?:manual|instructions?)\b|\b(?:calibration|conformance|quality|test)\s+certificates?\b|\b(?:manufacturer|product|equipment)\s+(?:quality|conformance|test)\s+certificates?\b/, "technical_documentation_fulfillment"],
  [/\bservice cent(?:er|re)\b.{0,100}\b(?:detail|address|contact|email|format|annexure|cover)\b|\b(?:detail|address|contact|email|format|annexure|cover)\b.{0,100}\bservice cent(?:er|re)\b|\bafter[ -]sales service term\b.{0,100}\b(?:agreed|address|contact)\b/, "service_capability_disclosure"],
  [/\b(?:iso|iec|astm|en\s*\d{3,}|din\s*\d{3,})\b.{0,40}\bcertificat(?:e|ion)\b|\bcertificat(?:e|ion)\b.{0,40}\b(?:iso|iec|astm|en\s*\d{3,}|din\s*\d{3,})\b/, "technical_standards_documentation"],
];

const TECHNICAL_SCOPE_PATTERNS: RegExp[] = [
  /\b(?:technical|specifications?|parameters?|equipment|instrument|product|device|system|machine|setup|apparatus|cryostat|laser|pump|microscope|spectrometer|optical|electrical|mechanical|environmental|material|ferromagnetic|stainless steel|alloy|standards?|test|measurement|accuracy|resolution|precision|repeatability|reproducibility|wavelength|voltage|current|power|frequency|dimensions?|capacity|range|tolerance|pressure|temperature|humidity|aperture|load|travel|noise|vacuum|interface|ports?|controller|motor|firmware|protocol|ingress protection|ip\d{2}|accessor(?:y|ies)|components?|modules?|fixtures?|jigs?|cutters?|templates?|clamps?|grips?|jaws?|specimens?|surfaces?|control|processor|graphics card|ssd|ram|memory|storage|ethernet|software|calibration|warranty|maintenance|installation|commissioning|training|acceptance|buttons?|switches?|fasteners?|bolts?|nuts?|grooves?|o[ -]?rings?)\b/i,
  /\b(?:astm|iso|iec|en\s*\d{3,}|din\s*\d{3,})\b.{0,100}\b(?:comply|complies|compliant|conform|conforms|meet|meets|standard|figure|fig\.)\b|\b(?:comply|complies|compliant|conform|conforms|meet|meets)\b.{0,80}\b(?:astm|iso|iec|en\s*\d{3,}|din\s*\d{3,}|figures?|fig\.)\b/i,
  /(?:≤|≥|±|<=|>=|\b\d+(?:\.\d+)?\s*(?:mm|cm|m|µm|um|nm|μm|kg|g|mg|l|ml|v|kv|mv|a|ma|w|kw|mw|hz|khz|mhz|ghz|bar|mbar|pa|kpa|°c|db|dbm|rpm|degrees?|%))\b/i,
];

const PRODUCT_REQUIREMENT_CLAUSE = /\b(?:shall|must|should|need(?:s)? to|is required to|be provided|be included|be equipped|have|has|enable|allow|capable|feature|features|include|includes|provide|providing|offer|offering|comply|complies|conform|conforms|match|matches|rectify|replace|repair|make available)\b.{0,100}\b(?:equipment|instrument|product|device|system|machine|unit|port|interface|fixture|jig|clamp|grip|jaw|component|module|processor|storage|memory|software|material|specimen|plate|surface|accessor(?:y|ies)|defects?|standard|figure|data|result|crosshead|testing|control|tools?|applications?|button|switch|bolt|nut)\b|\b(?:equipment|instrument|product|device|system|machine|unit|port|interface|fixture|jig|clamp|grip|jaw|component|module|processor|storage|memory|software|material|specimen|plate|surface|accessor(?:y|ies)|defects?|standard|figure|data|result|crosshead|testing|control|tools?|applications?|button|switch|bolt|nut)\b.{0,100}\b(?:shall|must|should|need(?:s)? to|is required to|be provided|be included|be equipped|have|has|enable|allow|capable|feature|features|include|includes|provide|providing|offer|offering|comply|complies|conform|conforms|match|matches|rectify|replace|repair|make available)\b/;

const MEASURABLE_PERFORMANCE_CLAUSE = /\b(?:shall|must|should|is required to)\b.{0,80}\b(?:retain|maintain|remain|withstand|accommodate|deliver|support|operate|measure|read|generate|store|hold|run|last|resist|perform|work)\b.{0,100}\b\d+(?:\.\d+)?\s*(?:days?|years?|hours?|minutes?|samples?|mm|cm|m|µm|um|nm|kg|g|mg|l|ml|v|kv|mv|a|ma|w|kw|hz|khz|mhz|ghz|bar|mbar|pa|kpa|°c|db|rpm|%)\b/i;

const CURRENT_SUPPLIER_FULFILLMENT = /\b(?:supplier|vendor|manufacturer|oem|contractor)\b.{0,120}\b(?:shall|must|will|is required to|undertakes? to|is responsible for)\b.{0,120}\b(?:deliver|supply|provide|install|commission|configure|train|calibrate|maintain|repair|replace|demonstrate|make available)\b.{0,140}\b(?:equipment|instrument|product|device|system|unit|accessor(?:y|ies)|software|staff|personnel|spare parts?|calibration|service|site|institute)\b|\b(?:shall|must|will|is required to)\b.{0,100}\b(?:deliver|supply|install|commission|configure|train|calibrate|maintain|repair|replace|demonstrate)\b.{0,140}\b(?:equipment|instrument|product|device|system|unit|accessor(?:y|ies)|software|spare parts?|service)\b/;

const DELIVERY_FULFILLMENT_CONTEXT = /\b(?:within|maximum within)\s+\d+\s+(?:calendar\s+)?days?\b.{0,100}\b(?:purchase order|\bpo\b)\b|\b(?:safe delivery|date of delivery|delivery period|delivery time|delivery date)\b|\b(?:purchase order|\bpo\b).{0,100}\b(?:within\s+\d+\s+(?:calendar\s+)?days?|\d+\s+days?)\b/;
const PACKAGE_HANDOFF_PROCEDURE = /\bpackage\b.{0,80}\b(?:opened|opening)\b.{0,80}\b(?:presence|representative)\b/;
const HISTORICAL_QUALIFICATION_CONTEXT = /\b(?:past performance|prior experience|similar orders?|previously executed|orders? have been executed|last (?:two|three|\d+) (?:years?|financial years?))\b/;

/**
 * Checklist confirmations and contact-information fields are not independently
 * assessable equipment or supplier-performance commitments. A form line can
 * contain words like "warranty" or "after-sales" that would otherwise satisfy
 * broad positive service patterns. Keep it visible for human scope review.
 *
 * Source section/form context is not passed into this classifier, so these
 * conservative quote-local tests must not claim to reconstruct document layout.
 */
const CHECKLIST_AGREEMENT_FIELD = /^\s*(?:(?:\(?[a-z0-9ivxlcdm]+\)?[.):]\s*)?)(?:warranty(?:\s+period)?|after[ -]sales(?:\s+service)?(?:\s+terms?)?|service(?:\s+terms?)?|maintenance(?:\s+terms?)?|delivery(?:\s+terms?)?|payment(?:\s+terms?)?|penalty(?:\s+clause)?)\s+(?:agreed|accepted|confirmed|acknowledged|complied)\b/i;
const SERVICE_CONTACT_INFORMATION_FIELD = /\b(?:service\s+cent(?:er|re)|after[ -]sales(?:\s+service)?)\b.{0,130}\b(?:contact(?:\s+(?:person|details?|number))?|details?|address|telephone|phone|mobile|e[ -]?mail|fax)\b|\b(?:contact(?:\s+(?:person|details?|number))?|details?|address|telephone|phone|mobile|e[ -]?mail|fax)\b.{0,130}\b(?:service\s+cent(?:er|re)|after[ -]sales(?:\s+service)?)\b/i;


/**
 * Classifies scope using source wording and clause function. Clear procurement
 * mechanics are excluded; conflicting technical/service context and unclear
 * fulfillment wording remain reviewable. A model label alone cannot admit an
 * otherwise unclassified requirement.
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
  // Guard form answers before broad service terms can promote them into the
  // accepted technical matrix. Human review can distinguish an actual local
  // service obligation from a bidder's contact-data disclosure.
  if (CHECKLIST_AGREEMENT_FIELD.test(text) || SERVICE_CONTACT_INFORMATION_FIELD.test(text)) {
    return {
      originalRowType,
      effectiveRowType: "ambiguous",
      outcome: "retained_for_review",
      reason: CHECKLIST_AGREEMENT_FIELD.test(text) ? "form_agreement_not_supplier_obligation" : "service_contact_form_requires_scope_review",
      requiresHumanReview: true,
    };
  }
  const administrativeMatches = ADMINISTRATIVE_PATTERNS.filter(([pattern]) => pattern.test(text));
  const serviceMatches = SERVICE_OBLIGATION_PATTERNS.filter(([pattern]) => pattern.test(text));
  const administrativeReasons = administrativeMatches.map(([, reason]) => reason);
  const serviceReasons = serviceMatches.map(([, reason]) => reason);
  const hasSupplierPerformanceFrame = /\b(?:supplier|vendor|contractor|manufacturer|oem)\b.{0,100}\b(?:shall|must|will|is required to|is responsible for|undertakes? to)\b|\b(?:shall|must|will|is required to|is responsible for|undertakes? to)\b.{0,100}\b(?:supplier|vendor|contractor|manufacturer|oem)\b/.test(text);
  const historicalQualificationOnly = administrativeReasons.includes("vendor_qualification_or_registration") && HISTORICAL_QUALIFICATION_CONTEXT.test(text);
  const hasTechnicalScope = !historicalQualificationOnly && (
    serviceMatches.length > 0
    || CURRENT_SUPPLIER_FULFILLMENT.test(text)
    || PRODUCT_REQUIREMENT_CLAUSE.test(text)
    || MEASURABLE_PERFORMANCE_CLAUSE.test(text)
    || TECHNICAL_SCOPE_PATTERNS.some((pattern) => pattern.test(text))
  );
  const hasConcreteTechnicalContent = !historicalQualificationOnly && (
    serviceMatches.length > 0
    || CURRENT_SUPPLIER_FULFILLMENT.test(text)
    || PRODUCT_REQUIREMENT_CLAUSE.test(text)
    || MEASURABLE_PERFORMANCE_CLAUSE.test(text)
    || /\b(?:product|equipment|instrument|device|system)\b.{0,100}\b(?:specification|parameter|standard|test|measurement|certificate|accessor(?:y|ies)|install|commission|deliver|supply|calibrate|maintain|train)\b|\b(?:specification|parameter|wavelength|voltage|frequency|dimension|capacity|tolerance|pressure|temperature|humidity|aperture|travel|vacuum|accuracy|resolution|calibration|commissioning|training|spare parts?)\b/.test(text)
    || /(?:≤|≥|±|<=|>=|\b\d+(?:\.\d+)?\s*(?:mm|cm|m|µm|um|nm|μm|kg|g|mg|l|ml|v|kv|mv|a|ma|w|kw|mw|hz|khz|mhz|ghz|bar|mbar|pa|kpa|°c|db|dbm|rpm|degrees?|%))\b/i.test(text)
  );
  const deliveryFulfillmentContext = DELIVERY_FULFILLMENT_CONTEXT.test(text)
    && (hasSupplierPerformanceFrame || /\b(?:vendor|supplier|manufacturer|equipment|instrument|product|system|device|indigenous|imported)\b/.test(text));
  const isDeliveryOrHandoffProcedure = administrativeReasons.includes("procurement_or_logistics_term")
    && (deliveryFulfillmentContext || /\b(?:safe delivery|date of delivery|delivery period|delivery time|delivery date)\b/.test(text));

  if (administrativeMatches.length > 0 && (
    serviceMatches.length > 0
    || hasTechnicalScope && (hasSupplierPerformanceFrame || hasConcreteTechnicalContent)
    || isDeliveryOrHandoffProcedure && !PACKAGE_HANDOFF_PROCEDURE.test(text)
  )) {
    return { originalRowType, effectiveRowType: "ambiguous", outcome: "retained_for_review", reason: "mixed_administrative_and_supplier_obligation", requiresHumanReview: true };
  }

  if (administrativeMatches.length > 0) {
    return { originalRowType, effectiveRowType: "instruction", outcome: "rejected", reason: administrativeReasons[0], requiresHumanReview: false };
  }

  if (serviceMatches.length > 0) {
    if (originalRowType === "instruction" || originalRowType === "ambiguous" || originalRowType === "unclassified" || !hasSupplierPerformanceFrame && serviceReasons.includes("technical_documentation_fulfillment")) {
      return { originalRowType, effectiveRowType: "requirement", outcome: "reclassified_for_review", reason: serviceReasons[0], requiresHumanReview: true };
    }
    return { originalRowType, effectiveRowType: "requirement", outcome: "kept", reason: serviceReasons[0], requiresHumanReview: false };
  }

  if (hasTechnicalScope) {
    if (originalRowType === "instruction" || originalRowType === "ambiguous" || originalRowType === "unclassified") {
      if (hasSupplierPerformanceFrame || CURRENT_SUPPLIER_FULFILLMENT.test(text)) {
        return { originalRowType, effectiveRowType: "requirement", outcome: "reclassified_for_review", reason: "source_grounded_technical_scope", requiresHumanReview: true };
      }
      return { originalRowType, effectiveRowType: "ambiguous", outcome: "retained_for_review", reason: "unresolved_instruction_classification", requiresHumanReview: true };
    }
    return { originalRowType, effectiveRowType: "requirement", outcome: "kept", reason: "source_grounded_technical_scope", requiresHumanReview: false };
  }

  if (originalRowType === "requirement") {
    return { originalRowType, effectiveRowType: "ambiguous", outcome: "retained_for_review", reason: "unresolved_requirement_scope", requiresHumanReview: true };
  }
  if (originalRowType === "instruction" || originalRowType === "ambiguous" || originalRowType === "unclassified") {
    return { originalRowType, effectiveRowType: "ambiguous", outcome: "retained_for_review", reason: originalRowType === "ambiguous" ? "unresolved_source_structure" : "unresolved_instruction_classification", requiresHumanReview: true };
  }
  return { originalRowType, effectiveRowType: "ambiguous", outcome: "retained_for_review", reason: "unresolved_candidate_scope", requiresHumanReview: true };
}

/** @deprecated Use classifyCandidateScope for all extracted candidate types. */
export const classifyInstructionCandidate = classifyCandidateScope;
