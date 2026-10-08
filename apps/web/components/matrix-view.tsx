"use client";

import { useEffect, useState } from "react";
import { RefreshCw, AlertCircle, CheckCircle, XCircle, Download } from "lucide-react";
import { api, MatrixRowResponse } from "@/lib/api/client";

interface MatrixViewProps {
  projectId: string;
  documentId: string;
  version: number;
}

const REVIEW_STATUS_LABELS: Record<string, string> = {
  unreviewed: "Unreviewed",
  reviewed: "Reviewed",
  needs_clarification: "Needs clarification",
  ocr_warning: "OCR warning",
};

function coverageAuditMessage(
  coverage:
    | {
        obligation_audit_status?: string;
        potential_omissions?: { pages: number[]; source_quote: string }[];
      }
    | undefined
): string | null {
  if (!coverage) return null;
  if (coverage.obligation_audit_status === "potential_omissions") {
    const findings = coverage.potential_omissions ?? [];
    const details = findings.slice(0, 3).map(({ pages, source_quote }) =>
      `${source_quote}${pages.length ? ` (page${pages.length === 1 ? "" : "s"} ${pages.join(", ")})` : ""}`
    );
    return `The independent obligation scan found ${findings.length} possible omission${findings.length === 1 ? "" : "s"}${details.length ? `: ${details.join("; ")}` : ""}. Review the source and add any missing requirement before exporting.`;
  }
  if (coverage.obligation_audit_status === "audit_failed") {
    return "The independent obligation scan failed or returned an unverifiable quote. Review the tender windows before exporting.";
  }
  if (coverage.obligation_audit_status === "not_available") {
    return "No independent obligation scan is available for this extraction. Completeness was not checked.";
  }
  return null;
}

function ReviewStatusBadge({ status }: { status: string }) {
  const label = REVIEW_STATUS_LABELS[status] ?? status;
  let icon: React.ReactNode = null;
  let className = "review-status-badge";

  switch (status) {
    case "reviewed":
      icon = <CheckCircle size={14} />;
      className += " reviewed";
      break;
    case "needs_clarification":
      icon = <XCircle size={14} />;
      className += " needs-clarification";
      break;
    case "ocr_warning":
      icon = <AlertCircle size={14} />;
      className += " ocr-warning";
      break;
    default:
      className += " unreviewed";
      break;
  }

  return (
    <span className={className}>
      {icon}
      <span>{label}</span>
    </span>
  );
}

export function MatrixView({ projectId, documentId, version }: MatrixViewProps) {
  const [rows, setRows] = useState<MatrixRowResponse[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportNotice, setExportNotice] = useState<string | null>(null);

  const loadMatrix = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.fetchMatrix(
        projectId,
        documentId,
        version
      );
      setRows(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load matrix");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadMatrix();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, documentId, version]);

  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    setExportNotice(null);
    try {
      // Trigger XLSX generation on the backend.
      const artifact = await api.createMatrixExport(
        projectId,
        documentId,
        version
      );

      if (artifact.status !== "completed") {
        if (artifact.validation_status === "needs_review") {
          const coverage = artifact.validation_report?.window_processing;
          const auditMessage = coverageAuditMessage(coverage);
          if (auditMessage) {
            setExportError(auditMessage);
            return;
          }
          if (coverage?.status === "incomplete") {
            const failedPages = Array.from(
              new Set(
                (coverage.failed_windows ?? []).flatMap((window) => window.pages)
              )
            ).sort((a, b) => a - b);
            const pageText = failedPages.length
              ? ` Affected tender pages: ${failedPages.join(", ")}.`
              : "";
            setExportError(
              `Extraction reached ${coverage.audited_windows ?? 0} of ${coverage.expected_windows ?? 0} source windows. Review the failed or missing windows before issuing a workbook.${pageText}`
            );
            return;
          }
          const count = artifact.validation_report?.source_validation?.issues.length ?? 0;
          setExportError(
            `${count} tender row${count === 1 ? " needs" : "s need"} source review before this workbook can be issued. Open the source citations and verify the exact wording.`
          );
          return;
        }
        if (artifact.validation_status === "failed") {
          const fields = Array.from(
            new Set(
              (artifact.validation_report?.issues ?? [])
                .map((issue) => issue.field)
                .filter((field): field is string => Boolean(field))
            )
          ).slice(0, 4);
          setExportError(
            fields.length
              ? `The generated workbook failed its content check in: ${fields.join(", ")}. No file was issued.`
              : "The generated workbook failed its content check. No file was issued."
          );
          return;
        }
        setExportError(
          `Export failed: ${artifact.error_message ?? "unknown error"}`
        );
        return;
      }
      if (artifact.validation_status !== "passed") {
        setExportError("The generated workbook did not pass validation and cannot be downloaded.");
        return;
      }

      // Download the generated workbook.
      const blob = await api.downloadMatrixExport(
        projectId,
        documentId,
        version,
        artifact.id
      );

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `tender_matrix_v${version}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      const coverage = artifact.validation_report?.window_processing;
      const coverageNotice =
        coverage?.status === "complete"
          ? ` Extraction calls completed for ${coverage.audited_windows ?? 0} of ${coverage.expected_windows ?? 0} source windows.`
          : coverage?.status === "not_available"
            ? " No extraction-window processing audit is available."
            : "";
      const obligationNotice =
        coverage?.obligation_audit_status === "no_potential_omissions"
          ? " The independent scan found no unmatched obligation excerpts; this is not proof that every obligation was identified."
          : " An independent obligation scan was not available, so whole-tender completeness is unverified.";
      setExportNotice(
        `All ${artifact.validation_report?.checked_columns ?? 0} exported columns and ${artifact.validation_report?.checked_cells ?? 0} cells passed the content check for ${artifact.validation_report?.actual_rows ?? rows?.length ?? 0} rows.${coverageNotice}${obligationNotice}`
      );
    } catch (err) {
      setExportError(
        err instanceof Error ? err.message : "Export failed"
      );
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="matrix-loading">
        <RefreshCw size={24} className="spin" />
        <span>Loading matrix…</span>
      </div>
    );
  }

  if (error || !rows) {
    return (
      <div className="empty-state">
        <AlertCircle size={32} aria-hidden="true" />
        <strong>{error ?? "No matrix data"}</strong>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="empty-state">
        <span>No requirements in this document version.</span>
      </div>
    );
  }

  // Highlight rows that need attention (unreviewed, needs_clarification, ocr_warning)
  const isUnresolved = (status: string) =>
    status === "unreviewed" ||
    status === "needs_clarification" ||
    status === "ocr_warning";

  return (
    <div className="matrix-wrapper">
      <div className="matrix-container">
        <table className="matrix-table">
          <thead>
            <tr>
              <th>S.No.</th>
              <th>Requirement ID</th>
              <th>Tender Requirement</th>
              <th>Category</th>
              <th>Clause</th>
              <th>Source Page</th>
              <th>Mandatory</th>
              <th>User Notes</th>
              <th>Review Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.requirement_id}
                className={isUnresolved(row.review_status) ? "unresolved" : ""}
              >
                <td>{row.serial}</td>
                <td className="mono">{row.requirement_id.slice(0, 8)}…</td>
                <td>{row.tender_requirement}</td>
                <td>{row.category ?? "—"}</td>
                <td>{row.clause ?? "—"}</td>
                <td>{row.source_page ?? "—"}</td>
                <td>
                  {row.mandatory === null ? "—" : row.mandatory ? "Yes" : "No"}
                </td>
                <td>{row.user_notes ?? "—"}</td>
                <td>
                  <ReviewStatusBadge status={row.review_status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="matrix-actions">
        <button
          type="button"
          className="button button-primary"
          onClick={handleExport}
          disabled={exporting}
        >
          {exporting ? (
            <>
              <RefreshCw size={14} className="spin" aria-hidden="true" />
              Exporting…
            </>
          ) : (
            <>
              <Download size={14} aria-hidden="true" />
              Export XLSX
            </>
          )}
        </button>
        {exportError && (
          <span className="error-text">{exportError}</span>
        )}
        {exportNotice && (
          <span className="matrix-export-notice" role="status">{exportNotice}</span>
        )}
      </div>
    </div>
  );
}
