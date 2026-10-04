"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle, Download, LockKeyhole, RefreshCw } from "lucide-react";

import {
  api,
  FinalMatrixRowResponse,
  SubmissionResponse,
} from "@/lib/api/client";

type ExportFormat = "xlsx" | "docx" | "pdf";

const statusLabel = (value: string | null) =>
  value ? value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "Unassessed";

export function FinalMatrixView(props: {
  projectId: string;
  documentId: string;
  version: number;
}) {
  const { projectId, documentId, version } = props;
  const [rows, setRows] = useState<FinalMatrixRowResponse[]>([]);
  const [submissions, setSubmissions] = useState<SubmissionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextRows, nextSubmissions] = await Promise.all([
        api.fetchFinalMatrix(projectId, documentId, version),
        api.fetchSubmissions(projectId),
      ]);
      setRows(nextRows);
      setSubmissions(nextSubmissions);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load final compliance data");
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

  const exportFile = async (format: ExportFormat) => {
    setBusy(`export-${format}`);
    setError(null);
    try {
      const artifact = await api.createFinalMatrixExport(
        projectId,
        documentId,
        version,
        format
      );
      if (artifact.status !== "completed") {
        throw new Error(artifact.error_message ?? "Export generation failed");
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
    <section style={{ marginTop: 28 }}>
      <div className="section-title-row">
        <div>
          <h2>Final compliance sheet</h2>
          <p>Evidence-backed status plus unresolved review state.</p>
        </div>
        <button className="button button-secondary button-small" type="button" onClick={() => void reload()}>
          <RefreshCw size={12} aria-hidden="true" /> Refresh
        </button>
      </div>

      {error ? <div className="upload-error-banner" role="alert"><AlertCircle size={14} />{error}</div> : null}

      <div className="normalized-card" style={{ marginBottom: 12 }}>
        <p>
          <strong>{rows.length}</strong> requirements · <strong>{unresolved.length}</strong> still require attention
        </p>
        <p className="field-help">
          Final export does not mean every row is compliant.
        </p>
      </div>

      <div className="matrix-container">
        <table className="matrix-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Tender requirement</th>
              <th>Vendor fact</th>
              <th>Evidence</th>
              <th>Assessment</th>
              <th>Human review</th>
              <th>Open issues</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const issues = [
                row.has_unresolved_conflict ? "Conflict" : null,
                row.clarification_statuses.some((s) => s === "pending") ? "Clarification" : null,
                row.deviation_statuses.some((s) => s === "proposed") ? "Deviation" : null,
              ].filter(Boolean);
              return (
                <tr key={row.requirement_id} className={issues.length || !row.assessment_is_confirmed ? "unresolved" : ""}>
                  <td>{row.serial}</td>
                  <td>{row.tender_requirement}</td>
                  <td>
                    {row.vendor_spec_value !== null
                      ? `${row.vendor_spec_parameter ?? "Value"}: ${row.vendor_spec_value} ${row.vendor_spec_unit ?? ""}`
                      : row.vendor_spec_source_text ?? "—"}
                  </td>
                  <td>{row.evidence_oem_document ? `${row.evidence_oem_document} · v${row.evidence_oem_version ?? "?"}` : "—"}</td>
                  <td>
                    <strong>{statusLabel(row.assessment_status)}</strong>
                    {row.assessment_reason_text ? <div className="field-help">{row.assessment_reason_text}</div> : null}
                  </td>
                  <td>
                    {row.assessment_is_confirmed ? (
                      <span><CheckCircle size={12} /> Confirmed</span>
                    ) : "Pending"}
                  </td>
                  <td>{issues.join(" · ") || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
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

      <div className="detail-panel" style={{ marginTop: 20 }}>
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
      </div>
    </section>
  );
}
