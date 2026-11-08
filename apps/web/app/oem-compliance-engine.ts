import type { ResponseSheet, ResponseSheetRow } from "./response-sheet";

export type BoundingBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type ProductDocumentPage = {
  pageNumber: number;
  text: string;
  lines?: Array<{
    text: string;
    bbox?: BoundingBox;
  }>;
};

export type ProductDocument = {
  id: string;
  name: string;
  type?: "datasheet" | "brochure" | "manual" | "oem_spec";
  pageCount: number;
  pages: ProductDocumentPage[];
  uploadedAt?: string;
};

export type ProductEvidenceCitation = {
  documentId: string;
  documentName: string;
  page: number;
  quote: string;
  bbox: BoundingBox | null;
  locationPrecision: "exact" | "approximate" | "page-only";
};

export type OEMComplianceStatus =
  | "COMPLIED"
  | "NOT_COMPLIED"
  | "DEVIATION"
  | "NEEDS_REVIEW"
  | "INSUFFICIENT_EVIDENCE";

export type OEMComplianceAssessment = {
  id: string;
  rowId: string;
  requirementId: string;
  status: OEMComplianceStatus;
  complianceLabel: "Complied" | "Not Complied" | "Deviation" | "Needs Review";
  offeredSpecification: string;
  reason: string;
  deviationRemarks?: string;
  tenderCitation: {
    page: number;
    quote: string;
    bbox: BoundingBox | null;
  };
  productCitation: ProductEvidenceCitation | null;
  requiresHumanReview: boolean;
  reviewReason?: string;
  reviewed: boolean;
  operatorOverride?: {
    status: "COMPLIED" | "NOT_COMPLIED" | "DEVIATION";
    remarks: string;
    timestamp?: string;
  };
};

export type ComplianceAssessmentReport = {
  documentId: string;
  productDocumentId: string;
  productDocumentName: string;
  evaluatedAt: string;
  summary: {
    totalRows: number;
    complied: number;
    notComplied: number;
    deviation: number;
    needsReview: number;
    insufficientEvidence: number;
  };
  assessments: OEMComplianceAssessment[];
};

// -------------------------------------------------------------
// Numerical & Range Extraction Helpers
// -------------------------------------------------------------

export type NumericConstraint =
  | { kind: "range"; min: number; max: number; unit: string }
  | { kind: "tolerance"; value: number; tolerance: number; unit: string }
  | { kind: "min"; min: number; unit: string }
  | { kind: "max"; max: number; unit: string }
  | { kind: "exact"; value: number; unit: string };

const RANGE_REGEX = /(-?\d+(?:\.\d+)?)\s*(?:to|-|–|—)\s*(-?\d+(?:\.\d+)?)\s*([a-zA-Z°%µ/]+(?:[a-zA-Z0-9/°%]+)?)/i;
const TOLERANCE_REGEX = /(?:±|\+\/-)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z°%µ/]+(?:[a-zA-Z0-9/°%]+)?)/i;
const VALUE_WITH_TOLERANCE_REGEX = /(-?\d+(?:\.\d+)?)\s*(?:±|\+\/-)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z°%µ/]+)?/i;
const MIN_REGEX = /(?:>=|min(?:imum)?|at least)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z°%µ/]+)?/i;
const MAX_REGEX = /(?:<=|max(?:imum)?|up to|at most)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z°%µ/]+)?/i;

export function extractNumericConstraint(text: string): NumericConstraint | null {
  if (!text) return null;

  // Check tolerance first: e.g. "±0.002 PSU" or "+/- 0.003 mS/cm"
  const tolMatch = text.match(TOLERANCE_REGEX);
  if (tolMatch) {
    const valWithTol = text.match(VALUE_WITH_TOLERANCE_REGEX);
    return {
      kind: "tolerance",
      value: valWithTol ? parseFloat(valWithTol[1]) : 0,
      tolerance: parseFloat(tolMatch[1]),
      unit: (tolMatch[2] || "").trim().toLowerCase(),
    };
  }

  // Check range: e.g. "0 to 70 mS/cm" or "-5 to 50 °C"
  const rangeMatch = text.match(RANGE_REGEX);
  if (rangeMatch) {
    return {
      kind: "range",
      min: parseFloat(rangeMatch[1]),
      max: parseFloat(rangeMatch[2]),
      unit: (rangeMatch[3] || "").trim().toLowerCase(),
    };
  }

  // Check minimum: e.g. ">= 4 hours" or "minimum 1000 records"
  const minMatch = text.match(MIN_REGEX);
  if (minMatch) {
    return {
      kind: "min",
      min: parseFloat(minMatch[1]),
      unit: (minMatch[2] || "").trim().toLowerCase(),
    };
  }

  // Check maximum: e.g. "<= 15 kg" or "up to 5000 m"
  const maxMatch = text.match(MAX_REGEX);
  if (maxMatch) {
    return {
      kind: "max",
      max: parseFloat(maxMatch[1]),
      unit: (maxMatch[2] || "").trim().toLowerCase(),
    };
  }

  // Check exact value: e.g. "18 kg", "6 hours", "230 V"
  const valMatch = text.match(/(?:^|\s)(\d+(?:\.\d+)?)\s*([a-zA-Z°%µ/]+(?:[a-zA-Z0-9/°%]+)?)/i);
  if (valMatch) {
    return {
      kind: "exact",
      value: parseFloat(valMatch[1]),
      unit: (valMatch[2] || "").trim().toLowerCase(),
    };
  }

  return null;
}

export function compareNumericConstraints(
  tender: NumericConstraint,
  product: NumericConstraint
): { status: OEMComplianceStatus; reason: string } {
  // If units are specified and incompatible
  if (tender.unit && product.unit && tender.unit !== product.unit) {
    return {
      status: "NEEDS_REVIEW",
      reason: `Different units detected (Tender: ${tender.unit}, Product: ${product.unit}). Operator verification required.`,
    };
  }

  // 1. Tolerance comparison (e.g. accuracy: lower tolerance is better)
  if (tender.kind === "tolerance" && product.kind === "tolerance") {
    if (product.tolerance <= tender.tolerance) {
      return {
        status: "COMPLIED",
        reason: `Offered accuracy (±${product.tolerance} ${product.unit}) complies with or exceeds required tolerance (±${tender.tolerance} ${tender.unit}).`,
      };
    } else {
      return {
        status: "DEVIATION",
        reason: `Offered tolerance (±${product.tolerance} ${product.unit}) is wider than required tolerance (±${tender.tolerance} ${tender.unit}).`,
      };
    }
  }

  // 2. Range comparison (product must fully encompass tender range)
  if (tender.kind === "range" && product.kind === "range") {
    if (product.min <= tender.min && product.max >= tender.max) {
      return {
        status: "COMPLIED",
        reason: `Offered measurement range (${product.min} to ${product.max} ${product.unit}) completely encompasses required range (${tender.min} to ${tender.max} ${tender.unit}).`,
      };
    } else {
      return {
        status: "DEVIATION",
        reason: `Offered range (${product.min} to ${product.max} ${product.unit}) does not fully cover required range (${tender.min} to ${tender.max} ${tender.unit}).`,
      };
    }
  }

  // 3. Minimum requirement (product min or value >= tender min)
  if (tender.kind === "min") {
    const prodVal = product.kind === "min" ? product.min : product.kind === "exact" ? product.value : product.kind === "range" ? product.max : null;
    if (prodVal !== null) {
      if (prodVal >= tender.min) {
        return {
          status: "COMPLIED",
          reason: `Offered value (${prodVal} ${tender.unit}) meets or exceeds required minimum of ${tender.min} ${tender.unit}.`,
        };
      } else {
        return {
          status: "NOT_COMPLIED",
          reason: `Offered value (${prodVal} ${tender.unit}) is below mandatory minimum of ${tender.min} ${tender.unit}.`,
        };
      }
    }
  }

  // 4. Maximum requirement (product max or value <= tender max)
  if (tender.kind === "max") {
    const prodVal = product.kind === "max" ? product.max : product.kind === "exact" ? product.value : product.kind === "range" ? product.max : null;
    if (prodVal !== null) {
      if (prodVal <= tender.max) {
        return {
          status: "COMPLIED",
          reason: `Offered value (${prodVal} ${tender.unit}) is within required limit of max ${tender.max} ${tender.unit}.`,
        };
      } else {
        return {
          status: "DEVIATION",
          reason: `Offered value (${prodVal} ${tender.unit}) exceeds required maximum of ${tender.max} ${tender.unit}.`,
        };
      }
    }
  }

  return {
    status: "NEEDS_REVIEW",
    reason: "Complex parameter specification requires operator review.",
  };
}

// -------------------------------------------------------------
// Product Document Search & Evidence Extraction
// -------------------------------------------------------------

export function findProductEvidence(
  queryText: string,
  productDoc: ProductDocument
): ProductEvidenceCitation | null {
  if (!queryText || !productDoc.pages.length) return null;

  // Clean and tokenize query keywords
  const normalizedQuery = queryText.toLowerCase().replace(/[^a-z0-9\s.]/g, " ");
  const keywords = normalizedQuery
    .split(/\s+/)
    .filter((w) => w.length > 2 && !["the", "and", "for", "with", "shall", "must", "unit", "system"].includes(w));

  if (keywords.length === 0) return null;

  let bestMatch: {
    pageNumber: number;
    sentence: string;
    matchedKeywords: number;
    bbox: BoundingBox | null;
  } | null = null;

  for (const page of productDoc.pages) {
    const sentences = page.text.split(/(?<=[.?!;\n])\s+/);
    for (const sentence of sentences) {
      const cleanSentence = sentence.trim();
      if (cleanSentence.length < 5) continue;

      const lowerSentence = cleanSentence.toLowerCase();
      let matchedCount = 0;
      for (const kw of keywords) {
        if (lowerSentence.includes(kw)) {
          matchedCount += 1;
        }
      }

      if (matchedCount > 0 && (!bestMatch || matchedCount > bestMatch.matchedKeywords)) {
        // Find line bounding box if lines available
        let bbox: BoundingBox | null = null;
        if (page.lines && page.lines.length > 0) {
          const matchingLine = page.lines.find((l) =>
            l.text.toLowerCase().includes(keywords[0])
          );
          if (matchingLine?.bbox) {
            bbox = matchingLine.bbox;
          }
        }

        bestMatch = {
          pageNumber: page.pageNumber,
          sentence: cleanSentence,
          matchedKeywords: matchedCount,
          bbox,
        };
      }
    }
  }

  if (bestMatch && bestMatch.matchedKeywords >= Math.min(2, keywords.length)) {
    return {
      documentId: productDoc.id,
      documentName: productDoc.name,
      page: bestMatch.pageNumber,
      quote: bestMatch.sentence,
      bbox: bestMatch.bbox,
      locationPrecision: bestMatch.bbox ? "exact" : "approximate",
    };
  }

  return null;
}

// -------------------------------------------------------------
// Core Compliance Evaluation Function
// -------------------------------------------------------------

export function evaluateRowCompliance(
  row: ResponseSheetRow,
  rowText: string,
  tenderCitation: { page: number; quote: string; bbox: BoundingBox | null },
  productDoc: ProductDocument
): OEMComplianceAssessment {
  const tenderConstraint = extractNumericConstraint(rowText);
  const evidence = findProductEvidence(rowText, productDoc);

  let status: OEMComplianceStatus = "INSUFFICIENT_EVIDENCE";
  let reason = "Specification not found in product documentation; supplier clarification required.";
  let offeredSpec = "";

  if (evidence) {
    offeredSpec = evidence.quote;
    const productConstraint = extractNumericConstraint(evidence.quote);

    if (tenderConstraint && productConstraint) {
      const comparison = compareNumericConstraints(tenderConstraint, productConstraint);
      status = comparison.status;
      reason = comparison.reason;
    } else {
      // Semantic check: if evidence matches affirmative features
      const lowerRow = rowText.toLowerCase();
      const lowerEvidence = evidence.quote.toLowerCase();

      // Contradiction signals
      if (
        lowerEvidence.includes("not supported") ||
        lowerEvidence.includes("optional") ||
        lowerEvidence.includes("not available") ||
        lowerEvidence.includes("not included")
      ) {
        status = "DEVIATION";
        reason = `Product documentation notes limitation or optional supply: "${evidence.quote}"`;
      } else if (
        lowerEvidence.includes("standard") ||
        lowerEvidence.includes("included") ||
        lowerEvidence.includes("built-in") ||
        lowerEvidence.includes("supplied") ||
        lowerEvidence.includes("integrated") ||
        lowerEvidence.includes("yes")
      ) {
        status = "COMPLIED";
        reason = `Documented as standard feature on page ${evidence.page}: "${evidence.quote}"`;
      } else {
        status = "COMPLIED";
        reason = `Verified against product datasheet on page ${evidence.page}: "${evidence.quote}"`;
      }
    }
  } else {
    // Missing evidence is NOT contradictory evidence (Rule from AGENTS.md)
    status = "INSUFFICIENT_EVIDENCE";
    reason = "No matching specification identified in product document. Marked for operator review.";
  }

  const labelMap: Record<OEMComplianceStatus, OEMComplianceAssessment["complianceLabel"]> = {
    COMPLIED: "Complied",
    NOT_COMPLIED: "Not Complied",
    DEVIATION: "Deviation",
    NEEDS_REVIEW: "Needs Review",
    INSUFFICIENT_EVIDENCE: "Needs Review",
  };

  return {
    id: `assess-${row.id}`,
    rowId: row.id,
    requirementId: row.sourceRequirementId || (row.sourceRequirementIds?.[0] ?? ""),
    status,
    complianceLabel: labelMap[status],
    offeredSpecification: offeredSpec || "To be confirmed by OEM",
    reason,
    deviationRemarks: status === "DEVIATION" ? reason : undefined,
    tenderCitation,
    productCitation: evidence,
    requiresHumanReview: status === "NEEDS_REVIEW" || status === "INSUFFICIENT_EVIDENCE" || status === "DEVIATION",
    reviewed: false,
  };
}

// -------------------------------------------------------------
// Evaluate Whole Sheet Against Product Documents
// -------------------------------------------------------------

export function evaluateSheetCompliance(
  sheet: ResponseSheet,
  tenderRequirements: Array<{ id: string; page: number; quote: string; bbox: BoundingBox | null }>,
  productDoc: ProductDocument,
  tenderTitle?: string
): ComplianceAssessmentReport {
  const assessments: OEMComplianceAssessment[] = [];

  for (const row of sheet.rows) {
    if (row.section) continue; // Skip pure section divider rows

    const tenderReq = tenderRequirements.find(
      (r) => r.id === row.sourceRequirementId || (row.sourceRequirementIds && row.sourceRequirementIds.includes(r.id))
    );

    const tenderCitation = {
      page: tenderReq?.page ?? 1,
      quote: tenderReq?.quote ?? row.values.join(" "),
      bbox: tenderReq?.bbox ?? null,
    };

    const rowText = row.values.filter(Boolean).join(" ");
    const assessment = evaluateRowCompliance(row, rowText, tenderCitation, productDoc);
    assessments.push(assessment);
  }

  const summary = {
    totalRows: assessments.length,
    complied: assessments.filter((a) => a.status === "COMPLIED").length,
    notComplied: assessments.filter((a) => a.status === "NOT_COMPLIED").length,
    deviation: assessments.filter((a) => a.status === "DEVIATION").length,
    needsReview: assessments.filter((a) => a.status === "NEEDS_REVIEW").length,
    insufficientEvidence: assessments.filter((a) => a.status === "INSUFFICIENT_EVIDENCE").length,
  };

  return {
    documentId: tenderTitle || "Tender Compliance",
    productDocumentId: productDoc.id,
    productDocumentName: productDoc.name,
    evaluatedAt: new Date().toISOString(),
    summary,
    assessments,
  };
}

// -------------------------------------------------------------
// Project Compliance Report to ResponseSheet (for UI & Export)
// -------------------------------------------------------------

export function projectComplianceReportToSheet(
  sheet: ResponseSheet,
  report: ComplianceAssessmentReport
): ResponseSheet {
  const assessmentMap = new Map<string, OEMComplianceAssessment>();
  for (const a of report.assessments) {
    assessmentMap.set(a.rowId, a);
  }

  const columns = [
    { header: "Tender Requirement", role: "requirement" as const },
    { header: "Tender Source", role: "page" as const },
    { header: "Compliance Status", role: "compliance" as const },
    { header: "Offered Specification & Technical Reason", role: "response" as const },
    { header: "OEM Evidence Citation", role: "source" as const },
    { header: "Deviation Remarks", role: "deviation" as const },
  ];

  const rows: ResponseSheetRow[] = sheet.rows.map((row) => {
    if (row.section) {
      return { ...row, values: [row.values[0] || "", "", "", "", "", ""] };
    }

    const assessment = assessmentMap.get(row.id);
    const tenderSourceText = assessment?.tenderCitation?.page ? `p. ${assessment.tenderCitation.page}` : `p. 1`;
    const complianceStatusText = assessment?.complianceLabel || "Needs Review";
    const offeredSpecAndReason = assessment
      ? `${assessment.offeredSpecification}\n\nTechnical Justification: ${assessment.reason}`
      : "Pending evaluation";
    const oemCitationText = assessment?.productCitation
      ? `${assessment.productCitation.documentName} (p. ${assessment.productCitation.page})`
      : "No OEM citation";
    const deviationText = assessment?.deviationRemarks || (assessment?.status === "DEVIATION" ? assessment.reason : "");

    const tenderReqText = row.values.filter(Boolean)[0] || "";

    return {
      ...row,
      values: [
        tenderReqText,
        tenderSourceText,
        complianceStatusText,
        offeredSpecAndReason,
        oemCitationText,
        deviationText,
      ],
    };
  });

  return {
    columns,
    rows,
    layout: "sectioned",
  };
}
