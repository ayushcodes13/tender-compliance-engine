export type PageTerminalState = "inspected" | "excluded" | "uncertain" | "failed" | "unvisited";
export type AnalysisCompletionStatus = "complete" | "partial";

export type PageTerminalStateRecord = {
  page: number;
  state: PageTerminalState;
  reason: string;
};

type PageCoverageInput = {
  page: number;
  routingDisposition: "selected" | "uncertain" | "excluded" | "unrouted" | "no_text";
  routingReason: string;
  routerMarkedUncertain: boolean;
  selectedForExtraction: boolean;
  extractionStatus: "not_selected" | "complete" | "incomplete";
};

export function derivePageTerminalState(page: PageCoverageInput): PageTerminalStateRecord {
  if (page.routingDisposition === "excluded") {
    if (page.routingReason.trim()) return { page: page.page, state: "excluded", reason: page.routingReason };
    return { page: page.page, state: "uncertain", reason: "The page was marked excluded without a recorded reason." };
  }
  if (page.routingDisposition === "uncertain" || page.routerMarkedUncertain) {
    return { page: page.page, state: "uncertain", reason: page.routingReason };
  }
  if (page.selectedForExtraction && page.extractionStatus === "incomplete") {
    return { page: page.page, state: "failed", reason: "Selected page extraction did not finish." };
  }
  if (page.routingDisposition === "selected" && page.selectedForExtraction && page.extractionStatus === "complete") {
    return { page: page.page, state: "inspected", reason: "Selected page extraction finished." };
  }
  return { page: page.page, state: "unvisited", reason: page.routingReason || "No terminal inspection or exclusion was recorded." };
}

export function deriveAnalysisCompletion(input: {
  expectedPageCount: number;
  pages: PageCoverageInput[];
  plannedInspectionStates: string[];
  hasPendingWork: boolean;
  coverageAuditIncomplete: boolean;
  roundBudgetExhausted: boolean;
}): {
  completionStatus: AnalysisCompletionStatus;
  pageTerminalStates: PageTerminalStateRecord[];
  completionReasons: string[];
} {
  const pageTerminalStates = [...input.pages]
    .sort((left, right) => left.page - right.page)
    .map(derivePageTerminalState);
  const reasons = new Set<string>();
  const expectedPages = Array.from({ length: Math.max(0, input.expectedPageCount) }, (_, index) => index + 1);
  const actualPages = pageTerminalStates.map((page) => page.page);
  if (input.expectedPageCount <= 0 || actualPages.length !== input.expectedPageCount
    || new Set(actualPages).size !== actualPages.length
    || expectedPages.some((page) => !actualPages.includes(page))) {
    reasons.add("page_state_inventory_incomplete");
  }
  if (pageTerminalStates.some((page) => page.state === "uncertain" || page.state === "failed" || page.state === "unvisited")) {
    reasons.add("unresolved_page_state");
  }
  if (input.plannedInspectionStates.some((state) => state !== "executed")) {
    reasons.add("unresolved_planner_action");
  }
  if (input.hasPendingWork) reasons.add("pending_work");
  if (input.coverageAuditIncomplete) reasons.add("incomplete_coverage_audit");
  if (input.roundBudgetExhausted) reasons.add("round_budget_exhausted");

  const completionReasons = [...reasons];
  return {
    completionStatus: completionReasons.length ? "partial" : "complete",
    pageTerminalStates,
    completionReasons,
  };
}

export function analysisExportFilename(filename: string, completionStatus: AnalysisCompletionStatus, extension: "docx" | "xlsx" | "pdf"): string {
  const baseName = filename.replace(/\.pdf$/i, "");
  const suffix = completionStatus === "partial" ? "-partial-draft" : "-technical-response";
  return `${baseName}${suffix}.${extension}`;
}
