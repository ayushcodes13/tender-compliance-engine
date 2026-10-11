"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle, Download, LockKeyhole, RefreshCw } from "lucide-react";
import Link from "next/link";
import { CitationEvidenceDrawer, CitationTarget } from "@/components/citation-evidence-drawer";

import {
  api,
  ExportArtifactResponse,
  FinalMatrixRowResponse,
  SubmissionResponse,
} from "@/lib/api/client";

type ExportFormat = "xlsx" | "docx" | "pdf";
type PotentialOmission = {
  window_index: number;
  pages: number[];
  source_quote: string;
  coverage_candidates?: { requirement_id: string; page_number: number; label: string }[];
};
type CoverageReviewDisplay = {
  page_number: number;
  source_quote: string;
  decision: "covered_by_requirement" | "not_in_scope";
  rationale: string | null;
  requirement_id: string | null;
  reviewed_at: string;
};
type SourceValidationFinding = { row_id: string; code: string };
type ZeroCandidateWindow = { window_index: number; chunk_id: string; pages: number[] };

function sourceValidationMessage(code: string): string {
  switch (code) {
    case "source_quote_not_found":
      return "Generated wording does not match the cited tender excerpt exactly.";
    case "ocr_visual_verification_required":
      return "OCR could not establish the exact wording; verify it on the cited page.";
    case "source_text_unavailable":
      return "Source text is unavailable for deterministic verification.";
    default:
      return "The cited source needs review before this export can be issued.";
  }
}

function coverageReviewKey(page: number, quote: string): string {
  return `${page}:${quote}`;
}

const statusLabel = (value: string | null) =>
  value ? value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "Unassessed";

function exportFieldSummary(issues: { field?: string }[] | undefined): string {
  const fields = Array.from(
    new Set(
      (issues ?? [])
        .map((issue) => issue.field)
        .filter((field): field is string => Boolean(field))
    )
  ).slice(0, 4);
  return fields.length ? ` Fields checked: ${fields.join(", ")}.` : "";
}

function safeDiagnosticCategories(values: (string | null | undefined)[]): string[] {
  return Array.from(
    new Set(
      values.filter(
        (value): value is string =>
          typeof value === "string" && /^[a-z0-9_]{1,64}$/i.test(value)
      )
    )
  );
}

function obligationCoverageMessage(
  coverage:
    | {
        obligation_audit_status?: string;
        potential_omissions?: { pages: number[]; source_quote: string }[];
        obligation_audit_failed_windows?: {
          coverage_error_category?: string | null;
        }[];
      }
    | undefined
): string | null {
  if (!coverage) return null;
  if (coverage.obligation_audit_status === "potential_omissions") {
    const excerpts = (coverage.potential_omissions ?? []).slice(0, 3).map((finding) => {
      const pages = finding.pages.length
        ? `page${finding.pages.length === 1 ? "" : "s"} ${finding.pages.join(", ")}`
        : "page unavailable";
      return `“${finding.source_quote}” (${pages})`;
    });
    const count = coverage.potential_omissions?.length ?? 0;
    const remaining = count - excerpts.length;
    return `The independent obligation scan found ${count} possible omission${count === 1 ? "" : "s"}${excerpts.length ? `: ${excerpts.join("; ")}` : ""}${remaining > 0 ? `; and ${remaining} more` : ""}. Review the source and add any missing requirement before exporting.`;
  }
  if (coverage.obligation_audit_status === "audit_failed") {
    const categories = safeDiagnosticCategories(
      (coverage.obligation_audit_failed_windows ?? []).map(
        (window) => window.coverage_error_category
      )
    );
    const categoryText = categories.length
      ? ` Diagnostic category${categories.length === 1 ? "" : "ies"}: ${categories.join(", ")}.`
      : "";
    const knownFindings = coverage.potential_omissions ?? [];
    const knownPages = Array.from(
      new Set(knownFindings.flatMap((finding) => finding.pages))
    ).sort((a, b) => a - b);
    const pageText = knownPages.length
      ? ` It also found possible omissions on page${knownPages.length === 1 ? "" : "s"} ${knownPages.join(", ")}.`
      : "";
    return `The independent obligation scan failed or returned an unverifiable quote. Review the tender windows before exporting.${pageText}${categoryText}`;
  }
  if (coverage.obligation_audit_status === "not_available") {
    return "No independent obligation scan is available for this extraction. Completeness was not checked.";
  }
  return null;
}

function obligationCoverageSummary(
  coverage:
    | {
        obligation_audit_status?: string;
        zero_candidate_windows?: ZeroCandidateWindow[];
      }
    | undefined
): string {
  const zeroCandidateNotice = zeroCandidateWindowSummary(coverage);
  if (coverage?.obligation_audit_status === "no_potential_omissions") {
    return ` The independent scan found no unmatched obligation excerpts, but it does not prove that every tender obligation was identified.${zeroCandidateNotice}`;
  }
  if (coverage?.obligation_audit_status === "potential_omissions") {
    return ` The independent scan found possible omissions that need human review.${zeroCandidateNotice}`;
  }
  if (coverage?.obligation_audit_status === "audit_failed") {
    return ` The independent scan did not complete, so whole-tender completeness needs human review.${zeroCandidateNotice}`;
  }
  return ` Whole-tender completeness was not verified because no independent obligation scan is available.${zeroCandidateNotice}`;
}

function zeroCandidateWindowSummary(
  coverage: { zero_candidate_windows?: ZeroCandidateWindow[] } | undefined
): string {
  const windows = coverage?.zero_candidate_windows ?? [];
  if (!windows.length) return "";
  const pages = Array.from(new Set(windows.flatMap((window) => window.pages))).sort(
    (a, b) => a - b
  );
  const pageText = pages.length ? ` on pages ${pages.join(", ")}` : " with no known page location";
  return ` ${windows.length} technical-section window${windows.length === 1 ? " had" : "s had"} no extracted rows${pageText}; review the source before relying on the sheet.`;
}

function sourceValidationDiagnostic(
  validation:
    | {
        llm_fallback_results?: {
          status: string;
          verdict?: "exact" | "not_exact" | "cannot_tell" | "unavailable" | "not_run";
          call_status?: string;
          error_category?: string | null;
        }[];
      }
    | undefined
): string {
  const results = validation?.llm_fallback_results ?? [];
  const categories = safeDiagnosticCategories(
    results
      .filter((result) => result.call_status === "failed")
      .map((result) => result.error_category)
  );
  const unavailableCount = results.filter(
    (result) => result.status === "image_unavailable"
  ).length;
  const details: string[] = [];
  if (categories.length) {
    details.push(`Image validation error category: ${categories.join(", ")}.`);
  }
  if (unavailableCount) {
    details.push(
      `The source page image could not be retrieved for ${unavailableCount} validation check${unavailableCount === 1 ? "" : "s"}.`
    );
  }
  const mismatchCount = results.filter(
    (result) => result.verdict === "not_exact"
  ).length;
  const uncertainCount = results.filter(
    (result) => result.verdict === "cannot_tell"
  ).length;
  if (mismatchCount) {
    details.push(
      `The page-image check found wording differences in ${mismatchCount} row${mismatchCount === 1 ? "" : "s"}.`
    );
  }
  if (uncertainCount) {
    details.push(
      `The page-image check could not determine the wording for ${uncertainCount} row${uncertainCount === 1 ? "" : "s"}.`
    );
  }
  return details.length ? ` ${details.join(" ")}` : "";
}

const statusTone = (value: string | null) => {
  if (value === "compliant") return "status-pill status-reviewed";
  if (value === "non_compliant") return "status-pill status-error";
  if (
    value === "conflict" ||
    value === "human_review_required" ||
    value === "not_demonstrated"
  ) {
    return "status-pill status-warning";
  }
  return "status-pill status-neutral";
};

function exportValidationLabel(artifact: ExportArtifactResponse): string {
  if (artifact.validation_status === "needs_review") return "Needs review";
  if (artifact.validation_status === "failed") return "Content check failed";
  if (artifact.status !== "completed") return "Generation failed";
  if (artifact.validation_status === "passed") return "Content checked";
  return "Not validated";
}

function exportValidationTone(artifact: ExportArtifactResponse): string {
  if (artifact.validation_status === "passed" && artifact.status === "completed") {
    return "status-pill status-reviewed";
  }
  if (artifact.validation_status === "needs_review") return "status-pill status-warning";
  if (artifact.validation_status === "failed") return "status-pill status-error";
  return "status-pill status-neutral";
}

function exportValidationSummary(artifact: ExportArtifactResponse): string {
  const report = artifact.validation_report;
  if (artifact.validation_status === "passed" && artifact.status === "completed") {
    if (!report) {
      return (
        "Content checks passed, but detailed counts are unavailable." +
        obligationCoverageSummary(undefined)
      );
    }
    const details: string[] = [];
    if (report.checked_columns !== undefined && report.checked_cells !== undefined) {
      details.push(`${report.checked_columns} columns and ${report.checked_cells} cells checked`);
    }
    if (report.actual_rows !== undefined) details.push(`across ${report.actual_rows} rows`);
    const llmRows = report?.source_validation?.llm_assisted_rows?.length ?? 0;
    const counts = details.length
      ? `${details.join(" ")}.`
      : "Detailed validation counts are unavailable in the saved report.";
    return (
      `${counts}${llmRows ? ` ${llmRows} row${llmRows === 1 ? " used" : "s used"} strict page-image review.` : ""}` +
      obligationCoverageSummary(report.window_processing)
    );
  }
  if (artifact.validation_status === "needs_review") {
    const issueCount =
      (report?.issues?.length ?? 0) +
      (report?.source_validation?.issues?.length ?? 0) +
      (report?.window_processing?.potential_omissions?.length ?? 0);
    return issueCount
      ? `${issueCount} validation or coverage finding${issueCount === 1 ? "" : "s"}. This export is unavailable for download until it has a passing result.${zeroCandidateWindowSummary(report?.window_processing)}`
      : `Validation could not establish a safe result. This export is unavailable for download.${zeroCandidateWindowSummary(report?.window_processing)}`;
  }
  if (artifact.validation_status === "failed") {
    return "The generated content did not match its saved requirements and source checks. No file was issued.";
  }
  if (artifact.status !== "completed") {
    return "The export could not be generated. No validated file is available.";
  }
  return "This artifact has no passing validation result and is unavailable for download.";
}

function exportGeneratedAt(value: string | null): string {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString();
}

export function FinalMatrixView(props: {
  projectId: string;
  documentId: string;
  version: number;
  documentName: string;
  technicalOnly?: boolean;
}) {
  const { projectId, documentId, version, documentName, technicalOnly = false } = props;
  const [citationDrawer, setCitationDrawer] = useState<CitationTarget | null>(null);
  const [rows, setRows] = useState<FinalMatrixRowResponse[]>([]);
  const [submissions, setSubmissions] = useState<SubmissionResponse[]>([]);
  const [exportArtifacts, setExportArtifacts] = useState<ExportArtifactResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [exportHistoryLoading, setExportHistoryLoading] = useState(true);
  const [exportHistoryError, setExportHistoryError] = useState<string | null>(null);
  const [historyDownloadError, setHistoryDownloadError] = useState<string | null>(null);
  const [historyDownloadId, setHistoryDownloadId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validationNotice, setValidationNotice] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [sourceValidationFindings, setSourceValidationFindings] = useState<
    SourceValidationFinding[]
  >([]);
  const [coverageFindings, setCoverageFindings] = useState<PotentialOmission[]>([]);
  const [zeroCandidateWindows, setZeroCandidateWindows] = useState<ZeroCandidateWindow[]>([]);
  const [coverageReviews, setCoverageReviews] = useState<Record<string, CoverageReviewDisplay>>({});
  const [coverageReviewDrafts, setCoverageReviewDrafts] = useState<Record<string, { requirementId: string; rationale: string }>>({});
  const [addedCoverageKeys, setAddedCoverageKeys] = useState<Set<string>>(new Set());
  const [coverageTypes, setCoverageTypes] = useState<Record<string, "obligation" | "prohibition" | "permission">>({});

  const reload = async () => {
    setLoading(true);
    setExportHistoryLoading(true);
    setError(null);
    setExportHistoryError(null);
    try {
      const [nextRows, nextSubmissions] = await Promise.all([
        api.fetchFinalMatrix(projectId, documentId, version),
        api.fetchSubmissions(projectId),
      ]);
      setRows(nextRows);
      setSubmissions(nextSubmissions);
      try {
        const savedCoverageReviews = await api.fetchCoverageReviews(
          projectId,
          documentId,
          version
        );
        setCoverageReviews(Object.fromEntries(
          savedCoverageReviews.map((review) => [
            coverageReviewKey(review.page_number, review.source_quote),
            {
              page_number: review.page_number,
              source_quote: review.source_quote,
              decision: review.decision,
              rationale: review.rationale,
              requirement_id: review.requirement_id,
              reviewed_at: review.created_at,
            },
          ])
        ));
      } catch {
        // The matrix remains readable if review-history retrieval is unavailable.
      }
      setExportHistoryError(null);
      try {
        setExportArtifacts(await api.fetchExports(projectId, documentId, version));
      } catch (historyErr) {
        setExportHistoryError(
          historyErr instanceof Error
            ? historyErr.message
            : "Failed to load export history"
        );
      } finally {
        setExportHistoryLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load final compliance data");
      setExportHistoryLoading(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, documentId, version]);

  const unresolved = useMemo(
    () =>
      rows.filter(
        (row) =>
          !row.assessment_is_confirmed ||
          row.has_unresolved_conflict ||
          row.assessment_status === "human_review_required" ||
          row.assessment_status === "not_demonstrated"
      ),
    [rows]
  );

  const summary = useMemo(
    () => ({
      compliant: rows.filter(
        (row) =>
          row.assessment_is_confirmed && row.assessment_status === "compliant"
      ).length,
      nonCompliant: rows.filter(
        (row) =>
          row.assessment_is_confirmed &&
          row.assessment_status === "non_compliant"
      ).length,
      confirmed: rows.filter((row) => row.assessment_is_confirmed).length,
    }),
    [rows]
  );

  const run = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(null);
    }
  };

  const downloadHistoricalExport = async (artifact: ExportArtifactResponse) => {
    if (artifact.status !== "completed" || artifact.validation_status !== "passed") {
      return;
    }
    setHistoryDownloadId(artifact.id);
    setHistoryDownloadError(null);
    try {
      const blob = await api.downloadExport(
        projectId,
        documentId,
        version,
        artifact.id
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      const extension = artifact.export_format ? `.${artifact.export_format}` : "";
      anchor.download = `tender_export_v${version}_${artifact.id.slice(0, 8)}${extension}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (downloadErr) {
      setHistoryDownloadError(
        downloadErr instanceof Error
          ? downloadErr.message
          : "Failed to download export"
      );
    } finally {
      setHistoryDownloadId(null);
    }
  };

  const addCoverageFinding = async (finding: PotentialOmission, page: number) => {
    const key = coverageReviewKey(page, finding.source_quote);
    setValidationNotice(null);
    const requirementType = coverageTypes[finding.source_quote];
    if (!requirementType) {
      setError("Choose whether the excerpt is an obligation, prohibition, or permission before adding it.");
      return;
    }
    setBusy(`coverage-${key}`);
    setError(null);
    try {
      await api.addRequirementFromSource(projectId, documentId, version, {
        page_number: page,
        source_quote: finding.source_quote,
        requirement_type: requirementType,
      });
      setAddedCoverageKeys((current) => new Set(current).add(key));
      setActionNotice("The excerpt was added as a source-linked, unreviewed requirement. Run an export again to recheck coverage.");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the source excerpt");
    } finally {
      setBusy(null);
    }
  };

  const recordCoverageReview = async (
    finding: PotentialOmission,
    page: number,
    decision: "covered_by_requirement" | "not_in_scope"
  ) => {
    const key = coverageReviewKey(page, finding.source_quote);
    const draft = coverageReviewDrafts[key];
    if (decision === "covered_by_requirement" && !draft?.requirementId) {
      setError("Select an active same-page requirement that covers this excerpt.");
      return;
    }
    if (decision === "not_in_scope" && !draft?.rationale.trim()) {
      setError(technicalOnly
        ? "Explain why this excerpt is not a technical specification."
        : "Explain why this excerpt is not a supplier requirement.");
      return;
    }
    setBusy(`review-${key}`);
    setError(null);
    try {
      const review = await api.reviewCoverageFinding(projectId, documentId, version, {
        page_number: page,
        source_quote: finding.source_quote,
        decision,
        ...(decision === "covered_by_requirement"
          ? { requirement_id: draft.requirementId }
          : { rationale: draft.rationale.trim() }),
      });
      setCoverageReviews((current) => ({
        ...current,
        [key]: {
          page_number: review.page_number,
          source_quote: review.source_quote,
          decision: review.decision,
          rationale: review.rationale,
          requirement_id: review.requirement_id,
          reviewed_at: review.created_at,
        },
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the coverage review");
    } finally {
      setBusy(null);
    }
  };

  const exportFile = async (format: ExportFormat) => {
    setBusy(`export-${format}`);
    setError(null);
    setValidationNotice(null);
    setActionNotice(null);
    setSourceValidationFindings([]);
    setCoverageFindings([]);
    setZeroCandidateWindows([]);
    try {
      const artifact = await api.createFinalMatrixExport(
        projectId,
        documentId,
        version,
        format
      );
      setExportArtifacts((current) => [
        artifact,
        ...current.filter((saved) => saved.id !== artifact.id),
      ]);
      setSourceValidationFindings(
        artifact.validation_report?.source_validation?.issues ?? []
      );
      setZeroCandidateWindows(
        artifact.validation_report?.window_processing?.zero_candidate_windows ?? []
      );
      if (artifact.status !== "completed") {
        if (artifact.validation_status === "failed") {
          const issueCount =
            (artifact.validation_report?.issues?.length ?? 0) +
            (artifact.validation_report?.source_validation?.issues.length ?? 0);
          throw new Error(
            `The generated file failed its content check (${issueCount} issue${issueCount === 1 ? "" : "s"}).${exportFieldSummary(artifact.validation_report?.issues)} No file was issued. Review the tender wording and source links, then try again.`
          );
        }
        if (artifact.validation_status === "needs_review") {
          const coverage = artifact.validation_report?.window_processing;
          if (coverage) {
            setCoverageFindings(coverage.potential_omissions ?? []);
            setCoverageReviews(Object.fromEntries(
              (coverage.resolved_omissions ?? []).map((review) => [
                coverageReviewKey(review.page_number, review.source_quote),
                {
                  page_number: review.page_number,
                  source_quote: review.source_quote,
                  decision: review.decision,
                  rationale: review.rationale,
                  requirement_id: review.requirement_id,
                  reviewed_at: review.reviewed_at,
                },
              ])
            ));
          }
          if (coverage?.potential_omissions?.length) {
            setCoverageFindings(coverage.potential_omissions);
          }
          if (coverage?.obligation_audit_status === "potential_omissions") {
            throw new Error(obligationCoverageMessage(coverage) ?? "Review possible omissions before exporting.");
          }
          const obligationMessage = obligationCoverageMessage(coverage);
          if (obligationMessage) throw new Error(obligationMessage);
          if (coverage?.status === "incomplete") {
            const failedPages = Array.from(
              new Set(
                (coverage.failed_windows ?? []).flatMap((window) => window.pages)
              )
            ).sort((a, b) => a - b);
            const pageText = failedPages.length
              ? ` Affected tender pages: ${failedPages.join(", ")}.`
              : "";
            throw new Error(
              `Extraction reached ${coverage.audited_windows ?? 0} of ${coverage.expected_windows ?? 0} source windows. Review the failed or missing windows before issuing this file.${pageText}`
            );
          }
          const issueCount = artifact.validation_report?.source_validation?.issues.length ?? 0;
          throw new Error(
            `${issueCount} tender row${issueCount === 1 ? " needs" : "s need"} source review before this file can be issued. Open each row's source citation and verify the exact wording.${sourceValidationDiagnostic(artifact.validation_report?.source_validation)}`
          );
        }
        throw new Error(artifact.error_message ?? "Export generation failed");
      }
      if (artifact.validation_status !== "passed") {
        throw new Error("The generated file did not complete its content check.");
      }
      const blob = await api.downloadExport(
        projectId,
        documentId,
        version,
        artifact.id
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `tender_compliance_v${version}.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      const llmCount =
        artifact.validation_report?.source_validation?.llm_assisted_rows?.length ?? 0;
      const coverage = artifact.validation_report?.window_processing;
      const coverageNotice =
        coverage?.status === "complete"
          ? ` Extraction calls completed for ${coverage.audited_windows ?? 0} of ${coverage.expected_windows ?? 0} source windows.`
          : coverage?.status === "not_available"
            ? " No extraction-window processing audit is available."
            : "";
      const obligationNotice = obligationCoverageSummary(coverage);
      setValidationNotice(
        `All ${artifact.validation_report?.checked_columns ?? 0} exported columns (${artifact.validation_report?.checked_cells ?? 0} cells) and source checks passed for ${artifact.validation_report?.actual_rows ?? rows.length} tender rows. ${llmCount ? `${llmCount} row${llmCount === 1 ? " was" : "s were"} checked with the strict page-image fallback.` : "All rows matched their saved source text directly."}${coverageNotice}${obligationNotice}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setBusy(null);
    }
  };

  const exportVendorResponseSheet = async () => {
    setBusy("export-vendor-response");
    setError(null);
    setValidationNotice(null);
    setSourceValidationFindings([]);
    setCoverageFindings([]);
    setZeroCandidateWindows([]);
    try {
      const artifact = await api.createVendorResponseSheetExport(
        projectId,
        documentId,
        version
      );
      setExportArtifacts((current) => [
        artifact,
        ...current.filter((saved) => saved.id !== artifact.id),
      ]);
      setSourceValidationFindings(
        artifact.validation_report?.source_validation?.issues ?? []
      );
      setZeroCandidateWindows(
        artifact.validation_report?.window_processing?.zero_candidate_windows ?? []
      );
      if (artifact.status !== "completed") {
        if (artifact.validation_status === "failed") {
          const issueCount =
            (artifact.validation_report?.issues?.length ?? 0) +
            (artifact.validation_report?.source_validation?.issues.length ?? 0);
          throw new Error(
            `The generated response sheet failed its content check (${issueCount} issue${issueCount === 1 ? "" : "s"}).${exportFieldSummary(artifact.validation_report?.issues)} No file was issued.`
          );
        }
        if (artifact.validation_status === "needs_review") {
          const coverage = artifact.validation_report?.window_processing;
          if (coverage) {
            setCoverageFindings(coverage.potential_omissions ?? []);
            setCoverageReviews(Object.fromEntries(
              (coverage.resolved_omissions ?? []).map((review) => [
                coverageReviewKey(review.page_number, review.source_quote),
                {
                  page_number: review.page_number,
                  source_quote: review.source_quote,
                  decision: review.decision,
                  rationale: review.rationale,
                  requirement_id: review.requirement_id,
                  reviewed_at: review.reviewed_at,
                },
              ])
            ));
          }
          if (coverage?.potential_omissions?.length) {
            setCoverageFindings(coverage.potential_omissions);
          }
          if (coverage?.obligation_audit_status === "potential_omissions") {
            throw new Error(obligationCoverageMessage(coverage) ?? "Review possible omissions before exporting.");
          }
          const obligationMessage = obligationCoverageMessage(coverage);
          if (obligationMessage) throw new Error(obligationMessage);
          if (coverage?.status === "incomplete") {
            const failedPages = Array.from(
              new Set(
                (coverage.failed_windows ?? []).flatMap((window) => window.pages)
              )
            ).sort((a, b) => a - b);
            const pageText = failedPages.length
              ? ` Affected tender pages: ${failedPages.join(", ")}.`
              : "";
            throw new Error(
              `Extraction reached ${coverage.audited_windows ?? 0} of ${coverage.expected_windows ?? 0} source windows. Review the failed or missing windows before issuing the response sheet.${pageText}`
            );
          }
          const issueCount = artifact.validation_report?.source_validation?.issues.length ?? 0;
          throw new Error(
            `${issueCount} tender row${issueCount === 1 ? " needs" : "s need"} source review before the response sheet can be issued.${sourceValidationDiagnostic(artifact.validation_report?.source_validation)}`
          );
        }
        throw new Error(artifact.error_message ?? "Export generation failed");
      }
      if (artifact.validation_status !== "passed") {
        throw new Error("The generated response sheet did not complete its content check.");
      }
      const blob = await api.downloadExport(
        projectId,
        documentId,
        version,
        artifact.id
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `tender_vendor_response_v${version}.docx`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      const llmCount =
        artifact.validation_report?.source_validation?.llm_assisted_rows?.length ?? 0;
      const coverage = artifact.validation_report?.window_processing;
      const coverageNotice =
        coverage?.status === "complete"
          ? ` Extraction calls completed for ${coverage.audited_windows ?? 0} of ${coverage.expected_windows ?? 0} source windows.`
          : coverage?.status === "not_available"
            ? " No extraction-window processing audit is available."
            : "";
      const obligationNotice = obligationCoverageSummary(coverage);
      setValidationNotice(
        `All ${artifact.validation_report?.checked_columns ?? 0} exported columns (${artifact.validation_report?.checked_cells ?? 0} cells) and source checks passed for ${artifact.validation_report?.actual_rows ?? rows.length} tender rows. ${llmCount ? `${llmCount} row${llmCount === 1 ? " was" : "s were"} checked with the strict page-image fallback.` : "All rows matched their saved source text directly."}${coverageNotice}${obligationNotice}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return <div className="matrix-loading"><RefreshCw size={20} className="spin" /> Loading final compliance sheet…</div>;
  }

  return (
    <>
    <section style={{ marginTop: 28 }}>
      <div className="section-title-row">
        <div>
          <h2>{technicalOnly ? "Tender technical specifications" : "Final compliance sheet"}</h2>
          <p>{technicalOnly
            ? "Source-linked rows extracted from the tender. Review them here, then download a blank response sheet for the OEM."
            : "Evidence-backed status plus unresolved review state."}</p>
        </div>
        <button className="button button-secondary button-small" type="button" onClick={() => void reload()}>
          <RefreshCw size={12} aria-hidden="true" /> Refresh
        </button>
      </div>

      {error ? <div className="upload-error-banner" role="alert"><AlertCircle size={14} />{error}</div> : null}
      {sourceValidationFindings.length ? (
        <section className="source-highlight-unavailable" aria-labelledby="source-validation-heading" style={{ marginTop: 12 }}>
          <strong id="source-validation-heading">Source wording findings</strong>
          <p>These rows did not pass the exact source check. Compare the generated wording with the immutable tender excerpt before trying the export again.</p>
          <ul>
            {sourceValidationFindings.map((finding) => {
              const row = rows.find((item) => item.requirement_id === finding.row_id);
              const pageNumber = row?.source_page;
              return (
                <li key={`${finding.row_id}-${finding.code}`} style={{ marginTop: 12 }}>
                  <strong>
                    {row
                      ? `Requirement ${row.serial}`
                      : `Requirement ${finding.row_id.slice(0, 8)}`} · {sourceValidationMessage(finding.code)}
                  </strong>
                  {row ? (
                    <>
                      <p><span>Generated wording:</span> {row.tender_requirement}</p>
                      <p><span>Saved source excerpt:</span> <mark>{row.raw_source || "Source excerpt unavailable"}</mark></p>
                      {pageNumber ? (
                        <button
                          type="button"
                          className="button button-secondary button-small"
                          onClick={() => setCitationDrawer({
                            projectId,
                            documentId,
                            documentName,
                            version,
                            pageNumber,
                            requirementId: row.requirement_id,
                            sourceId: row.source_anchor_id ?? null,
                            quoteText: row.raw_source,
                            clause: row.clause,
                          })}
                        >
                          Open cited page {pageNumber}
                        </button>
                      ) : (
                        <p>Source location unavailable; no page was inferred.</p>
                      )}
                    </>
                  ) : (
                    <p>The requirement is no longer in the current matrix. Refresh the sheet before reviewing this finding.</p>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
      {coverageFindings.length || Object.keys(coverageReviews).length ? (
        <div className="source-highlight-unavailable" role="alert" style={{ marginTop: 12 }}>
          <strong>{technicalOnly ? "Possible missing technical specifications" : "Coverage review"}</strong>
          <ul>
            {coverageFindings.map((finding, index) => (
              <li key={`${finding.pages.join("-")}-${index}`} style={{ marginTop: 10 }}>
                <p><mark>{finding.source_quote}</mark></p>
                {finding.pages.map((page) => {
                  const key = coverageReviewKey(page, finding.source_quote);
                  const review = coverageReviews[key];
                  const candidates = (finding.coverage_candidates ?? []).filter(
                    (candidate) => candidate.page_number === page
                  );
                  const draft = coverageReviewDrafts[key] ?? {
                    requirementId: "",
                    rationale: "",
                  };
                  return (
                    <div key={page} style={{ marginTop: 10, paddingLeft: 12, borderLeft: "2px solid var(--border-subtle)" }}>
                      <Link
                        className="text-action"
                        href={`/projects/${projectId}/review?documentId=${encodeURIComponent(documentId)}&version=${version}&page=${page}&sourceQuote=${encodeURIComponent(finding.source_quote)}`}
                      >
                        Open tender page {page} and inspect excerpt
                      </Link>
                      {review ? (
                        <p role="status" style={{ margin: "8px 0 0" }}>
                          Review recorded: {review.decision === "not_in_scope"
                            ? technicalOnly ? "not a technical specification" : "not a supplier requirement"
                            : "covered by an existing requirement"} · {new Date(review.reviewed_at).toLocaleString()}
                          {review.rationale ? ` · ${review.rationale}` : ""}
                          <span> Run an export again to confirm this finding is resolved.</span>
                        </p>
                      ) : (
                        <>
                          <label className="form-field" style={{ marginTop: 8, maxWidth: 420 }}>
                        {technicalOnly ? "Existing technical specification that covers this excerpt" : "Existing requirement that covers this excerpt"}
                            <select
                              value={draft.requirementId}
                              onChange={(event) => setCoverageReviewDrafts((current) => ({
                                ...current,
                                [key]: { ...draft, requirementId: event.target.value },
                              }))}
                            >
                              <option value="">Choose same-page requirement</option>
                              {candidates.map((row) => (
                                <option key={row.requirement_id} value={row.requirement_id}>
                                  {row.label.slice(0, 180)}
                                </option>
                              ))}
                            </select>
                          </label>
                          <button
                            type="button"
                            className="button button-secondary button-small"
                            style={{ margin: "8px 8px 0 0" }}
                            disabled={!draft.requirementId || busy === `review-${key}`}
                            onClick={() => void recordCoverageReview(finding, page, "covered_by_requirement")}
                          >
                            {busy === `review-${key}` ? "Saving…" : "Mark as already covered"}
                          </button>
                          <label className="form-field" style={{ marginTop: 12, maxWidth: 520 }}>
                            {technicalOnly ? "Why this is not a technical specification" : "Why this is not a supplier requirement"}
                            <textarea
                              value={draft.rationale}
                              maxLength={2000}
                              rows={2}
                              onChange={(event) => setCoverageReviewDrafts((current) => ({
                                ...current,
                                [key]: { ...draft, rationale: event.target.value },
                              }))}
                            />
                          </label>
                          <button
                            type="button"
                            className="button button-secondary button-small"
                            disabled={!draft.rationale.trim() || busy === `review-${key}`}
                            onClick={() => void recordCoverageReview(finding, page, "not_in_scope")}
                          >
                            {busy === `review-${key}` ? "Saving…" : technicalOnly ? "Mark not a technical specification" : "Mark not a supplier requirement"}
                          </button>
                        </>
                      )}
                    </div>
                  );
                })}
                <label className="form-field" style={{ marginTop: 8, maxWidth: 320 }}>
                  {technicalOnly ? "Technical-specification row type" : "Requirement type"}
                  <select
                    value={coverageTypes[finding.source_quote] ?? ""}
                    onChange={(event) => setCoverageTypes((current) => ({
                      ...current,
                      [finding.source_quote]: event.target.value as "obligation" | "prohibition" | "permission",
                    }))}
                  >
                    <option value="">Choose type</option>
                    <option value="obligation">Obligation</option>
                    <option value="prohibition">Prohibition</option>
                    <option value="permission">Permission</option>
                  </select>
                </label>
                {finding.pages.map((page) => {
                  const key = coverageReviewKey(page, finding.source_quote);
                  const added = addedCoverageKeys.has(key);
                  return (
                    <button
                      key={`add-${page}`}
                      type="button"
                      className="button button-secondary button-small"
                      style={{ margin: "8px 8px 0 0" }}
                      disabled={added || !coverageTypes[finding.source_quote] || busy === `coverage-${key}`}
                      onClick={() => void addCoverageFinding(finding, page)}
                    >
                      {added ? "Added for review" : busy === `coverage-${key}` ? "Adding…" : technicalOnly ? "Add excerpt as unreviewed technical specification" : "Add excerpt as unreviewed requirement"}
                    </button>
                  );
                })}
              </li>
            ))}
            {Object.values(coverageReviews)
              .filter((review) => !coverageFindings.some(
                (finding) => finding.source_quote === review.source_quote && finding.pages.includes(review.page_number)
              ))
              .map((review) => (
                <li key={coverageReviewKey(review.page_number, review.source_quote)} style={{ marginTop: 10 }}>
                  <p><mark>{review.source_quote}</mark></p>
                  <p role="status">
                    Page {review.page_number}: {review.decision === "not_in_scope"
                      ? technicalOnly ? "not a technical specification" : "not a supplier requirement"
                      : "covered by an existing requirement"} · {new Date(review.reviewed_at).toLocaleString()}
                    {review.rationale ? ` · ${review.rationale}` : ""}
                  </p>
                </li>
              ))}
          </ul>
        </div>
      ) : null}
      {zeroCandidateWindows.length ? (
        <section
          className="source-highlight-unavailable"
          aria-labelledby="zero-candidate-heading"
          role="alert"
          style={{ marginTop: 12 }}
        >
          <strong id="zero-candidate-heading">
            {zeroCandidateWindows.length} technical-section window{zeroCandidateWindows.length === 1 ? "" : "s"} had no extracted rows
          </strong>
          <p>
            This may be a heading or continuation with no separate requirement, or a missed specification. The export content check validates rows that were generated; it cannot confirm that these pages contain nothing else. Review each page before relying on the sheet.
          </p>
          <ul>
            {zeroCandidateWindows.map((window) => (
              <li key={`${window.window_index}-${window.chunk_id}`} style={{ marginTop: 8 }}>
                Window {window.window_index}: {window.pages.length ? window.pages.map((page, index) => (
                  <span key={page}>
                    {index > 0 ? ", " : ""}
                    <Link
                      className="text-action"
                      href={`/projects/${projectId}/review?documentId=${encodeURIComponent(documentId)}&version=${version}&page=${page}`}
                    >
                      page {page}
                    </Link>
                  </span>
                )) : "source page unavailable"}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {validationNotice ? (
        <div className="compliance-ready-banner" role="status">
          <CheckCircle size={15} aria-hidden="true" />
          <div><strong>Export content check passed.</strong><span>{validationNotice}</span></div>
        </div>
      ) : null}
      {actionNotice ? (
        <div className="compliance-attention-banner" role="status">
          <AlertCircle size={15} aria-hidden="true" />
          <div><strong>Requirement added for review.</strong><span>{actionNotice}</span></div>
        </div>
      ) : null}

      {!technicalOnly ? <div className="compliance-summary-grid" aria-label="Compliance sheet summary">
        <div className="compliance-summary-card">
          <span>Total requirements</span>
          <strong>{rows.length}</strong>
          <small>{summary.confirmed} human-confirmed</small>
        </div>
        <div className="compliance-summary-card compliance-summary-good">
          <span>Compliant</span>
          <strong>{summary.compliant}</strong>
          <small>Confirmed against evidence</small>
        </div>
        <div className="compliance-summary-card compliance-summary-bad">
          <span>Non-compliant</span>
          <strong>{summary.nonCompliant}</strong>
          <small>Confirmed technical gaps</small>
        </div>
        <div className="compliance-summary-card compliance-summary-warning">
          <span>Needs attention</span>
          <strong>{unresolved.length}</strong>
          <small>Unconfirmed, missing evidence, or conflict</small>
        </div>
      </div> : null}

      {!technicalOnly && unresolved.length > 0 ? (
        <div className="compliance-attention-banner" role="status">
          <AlertCircle size={15} aria-hidden="true" />
          <div>
            <strong>{unresolved.length} rows still need review.</strong>
            <span>
              They remain visible in exports. Generating a file does not mark
              them compliant.
            </span>
          </div>
        </div>
      ) : !technicalOnly ? (
        <div className="compliance-ready-banner" role="status">
          <CheckCircle size={15} aria-hidden="true" />
          <div>
            <strong>Every row has a human-confirmed assessment.</strong>
            <span>Review the final source links before locking a submission.</span>
          </div>
        </div>
      ) : null}

      <div className="matrix-container">
        <table className="matrix-table">
          <thead>
            <tr>
              <th>#</th>
              <th>{technicalOnly ? "Technical specification from tender" : "Tender requirement"}</th>
              <th>Tender source</th>
              {!technicalOnly ? <>
                <th>Vendor fact</th>
                <th>Evidence</th>
                <th>Assessment</th>
                <th>Human review</th>
                <th>Open issues</th>
              </> : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const sourcePage =
                Number.isInteger(row.source_page) && (row.source_page ?? 0) > 0
                  ? row.source_page
                  : null;
              const issues = [
                row.has_unresolved_conflict ? "Conflict" : null,
                row.clarification_statuses.some((s) => s === "pending") ? "Clarification" : null,
                row.deviation_statuses.some((s) => s === "proposed") ? "Deviation" : null,
              ].filter(Boolean);
              return (
                <tr key={row.requirement_id} className={!technicalOnly && (issues.length || !row.assessment_is_confirmed) ? "unresolved" : ""}>
                  <td>{row.serial}</td>
                  <td>{row.tender_requirement}</td>
                  <td>
                    {sourcePage !== null ? (
                      <a
                        className="button button-secondary button-small"
                        href={`/projects/${projectId}/review?documentId=${encodeURIComponent(documentId)}&version=${version}&requirementId=${encodeURIComponent(row.requirement_id)}&page=${sourcePage}${row.source_anchor_id ? `&sourceId=${encodeURIComponent(row.source_anchor_id)}` : ""}`}
                        aria-label={`Open tender source for requirement ${row.serial}, page ${sourcePage}`}
                        onClick={(event) => {
                          event.preventDefault();
                          setCitationDrawer({ projectId, documentId, documentName, version, pageNumber: sourcePage, requirementId: row.requirement_id, sourceId: row.source_anchor_id ?? null, quoteText: row.raw_source, clause: row.clause });
                        }}
                      >
                        Page {sourcePage} · Open source
                      </a>
                    ) : (
                      <span>Location unavailable</span>
                    )}
                  </td>
                  {!technicalOnly ? <>
                  <td>
                    {typeof row.vendor_spec_value === "number"
                      ? `${row.vendor_spec_parameter ?? "Value"}: ${row.vendor_spec_value}${row.vendor_spec_unit ? ` ${row.vendor_spec_unit}` : ""}`
                      : row.vendor_spec_source_text || "—"}
                  </td>
                  <td>{row.evidence_oem_document ? `${row.evidence_oem_document} · v${row.evidence_oem_version ?? "?"}` : "—"}</td>
                  <td>
                    <span className={statusTone(row.assessment_status)}>
                      {statusLabel(row.assessment_status)}
                    </span>
                    {row.assessment_reason_text ? <div className="field-help">{row.assessment_reason_text}</div> : null}
                  </td>
                  <td>
                    {row.assessment_is_confirmed ? (
                      <span><CheckCircle size={12} /> Confirmed</span>
                    ) : "Pending"}
                  </td>
                  <td>{issues.join(" · ") || "—"}</td>
                  </> : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {!technicalOnly ? <div className="export-panel">
        <div>
          <strong>Export compliance sheet</strong>
          <p>Download the current source-linked matrix. Unresolved rows remain visible.</p>
        </div>
        <div className="matrix-actions" style={{ flexWrap: "wrap" }}>
        {(["xlsx", "docx", "pdf"] as ExportFormat[]).map((format) => (
          <button
            key={format}
            className="button button-secondary"
            type="button"
            disabled={busy !== null}
            onClick={() => void exportFile(format)}
          >
            <Download size={14} aria-hidden="true" />
            {busy === `export-${format}` ? "Generating…" : `Export ${format.toUpperCase()}`}
          </button>
        ))}
        </div>
      </div> : null}

      <div className="export-panel" style={{ marginTop: 12 }}>
        <div>
          <strong>{technicalOnly ? "Download OEM response sheet" : "Prepare a vendor response sheet"}</strong>
          <p>{technicalOnly
            ? "Keeps the tender’s original technical wording and provides blank response fields for the OEM."
            : "Exports the tender requirements with blank OEM compliance and deviation fields."}</p>
        </div>
        <button
          className="button button-secondary"
          type="button"
          disabled={busy !== null}
          onClick={() => void exportVendorResponseSheet()}
        >
          <Download size={14} aria-hidden="true" />
          {busy === "export-vendor-response" ? "Generating…" : technicalOnly ? "Download response sheet (DOCX)" : "Export vendor response DOCX"}
        </button>
      </div>

      <div className="detail-panel" style={{ marginTop: 20 }}>
        <div className="section-title-row">
          <div>
            <h2>Export history</h2>
            <p>Exports for tender version {version}. Only completed exports with a passing validation result can be downloaded.</p>
          </div>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={exportHistoryLoading}
            onClick={() => void reload()}
            aria-label="Refresh export history"
          >
            <RefreshCw size={12} aria-hidden="true" /> Refresh
          </button>
        </div>

        {exportHistoryError ? (
          <div className="upload-error-banner" role="alert">{exportHistoryError}</div>
        ) : null}
        {historyDownloadError ? (
          <div className="upload-error-banner" role="alert">{historyDownloadError}</div>
        ) : null}
        {exportHistoryLoading && exportArtifacts.length === 0 ? (
          <div className="empty-state">Loading export history…</div>
        ) : exportArtifacts.length === 0 && exportHistoryError ? (
          <div className="empty-state"><strong>Export history could not be loaded.</strong></div>
        ) : exportArtifacts.length === 0 ? (
          <div className="empty-state"><strong>No exports for this tender version yet.</strong></div>
        ) : (
          <div className="matrix-container">
            <table className="doclist-table">
              <thead>
                <tr><th>Format</th><th>Generated</th><th>Validation</th><th>Validation details</th><th>Download</th></tr>
              </thead>
              <tbody>
                {exportArtifacts.map((artifact) => {
                  const passed = artifact.status === "completed" && artifact.validation_status === "passed";
                  return (
                    <tr key={artifact.id}>
                      <td>{artifact.export_format?.toUpperCase() ?? "Export"}</td>
                      <td>{exportGeneratedAt(artifact.generated_at)}</td>
                      <td><span className={exportValidationTone(artifact)}>{exportValidationLabel(artifact)}</span></td>
                      <td>{exportValidationSummary(artifact)}</td>
                      <td>
                        {passed ? (
                          <button
                            className="button button-secondary button-small"
                            type="button"
                            disabled={historyDownloadId !== null}
                            onClick={() => void downloadHistoricalExport(artifact)}
                          >
                            <Download size={12} aria-hidden="true" />
                            {historyDownloadId === artifact.id ? "Downloading…" : "Download"}
                          </button>
                        ) : <span>Unavailable</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {!technicalOnly ? <div className="detail-panel" style={{ marginTop: 20 }}>
        <div className="section-title-row">
          <div>
            <h2>Submission versions</h2>
            <p>Locking freezes a snapshot. Approval records the human approver.</p>
          </div>
          <button
            className="button button-primary button-small"
            type="button"
            disabled={busy !== null}
            onClick={() => void run("create-submission", () => api.createSubmission(projectId, documentId, version))}
          >
            Create draft submission
          </button>
        </div>

        {submissions.length === 0 ? (
          <div className="empty-state"><strong>No submission versions yet.</strong></div>
        ) : (
          <table className="doclist-table">
            <thead>
              <tr><th>Version</th><th>Status</th><th>Snapshot</th><th>Approved</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {submissions.map((sub) => (
                <tr key={sub.id}>
                  <td>v{sub.version_number}</td>
                  <td>{statusLabel(sub.status)}</td>
                  <td>{sub.matrix_sha256.slice(0, 12)}…</td>
                  <td>{sub.approved_at ? new Date(sub.approved_at).toLocaleString() : "—"}</td>
                  <td>
                    <div className="inline-actions">
                      {sub.status === "draft" ? (
                        <button className="button button-secondary button-small" type="button"
                          onClick={() => void run(`lock-${sub.id}`, () => api.lockSubmission(projectId, sub.id))}>
                          <LockKeyhole size={12} /> Lock
                        </button>
                      ) : null}
                      {sub.status === "locked" ? (
                        <button className="button button-primary button-small" type="button"
                          onClick={() => void run(`approve-${sub.id}`, () => api.approveSubmission(projectId, sub.id))}>
                          Approve
                        </button>
                      ) : null}
                      {sub.status === "approved" ? (
                        <button className="button button-secondary button-small" type="button"
                          onClick={() => void run(`revoke-${sub.id}`, () => api.revokeSubmission(projectId, sub.id, "Revoked from browser review"))}>
                          Revoke
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div> : null}
    </section>
    <CitationEvidenceDrawer citation={citationDrawer} onClose={() => setCitationDrawer(null)} />
    </>
  );
}
