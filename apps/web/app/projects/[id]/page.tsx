"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  ArrowLeft,
  FileText,
  Pencil,
  Save,
  X,
  Upload,
  File,
  RefreshCw,
  Check,
  AlertCircle,
} from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { OemDocumentsPanel } from "@/components/oem-documents-panel";
import { ProjectFlowNav } from "@/components/project-flow-nav";
import {
  api,
  Project,
  DocumentItem,
  ProcessingRun,
  UploadResponse,
} from "@/lib/api/client";

function statusLabel(status: Project["status"]): string {
  switch (status) {
    case "draft":
      return "Draft";
    case "tender_uploaded":
      return "Tender uploaded";
    case "documents_processing":
      return "Processing";
    case "requirements_extracted":
      return "Extracted";
    case "review_in_progress":
      return "In review";
    case "matrix_ready":
      return "Compliance sheet ready";
    case "exported":
      return "Exported";
    case "archived":
      return "Archived";
    default:
      return status;
  }
}

function formatDate(date: string): string {
  return new Date(date).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function documentProcessingMeta(
  status: DocumentItem["processing_status"]
): { label: string; className: string; help: string } {
  switch (status) {
    case "uploaded":
    case "queued":
      return {
        label: "Waiting to process",
        className: "status-neutral",
        help: "The document is safely uploaded and waiting for the worker.",
      };
    case "processing":
      return {
        label: "Processing",
        className: "status-warning",
        help: "Parsing, OCR, and requirement extraction are running.",
      };
    case "parsed":
      return {
        label: "Ready for review",
        className: "status-reviewed",
        help: "Processing completed. Review the extracted requirements next.",
      };
    case "ocr_warning":
      return {
        label: "Ready with OCR warning",
        className: "status-warning",
        help: "Processing completed, but OCR-sensitive source text needs review.",
      };
    case "partial":
      return {
        label: "Partially processed",
        className: "status-warning",
        help: "Some processing completed. You can review what is available or retry.",
      };
    case "failed":
      return {
        label: "Processing failed",
        className: "status-error",
        help: "Processing stopped safely. No compliance result was invented.",
      };
  }
}

function processingStageLabel(stage: ProcessingRun["stage"]): string {
  switch (stage) {
    case "parse":
      return "Document parsing";
    case "ocr":
      return "Text recognition (OCR)";
    case "cleanup":
      return "Text cleanup";
    case "extract":
      return "Requirement extraction";
  }
}

function processingStatusLabel(status: ProcessingRun["status"]): string {
  switch (status) {
    case "started":
      return "started";
    case "running":
      return "in progress";
    case "completed":
      return "completed";
    case "failed":
      return "failed";
    case "retry":
      return "will retry";
  }
}

export default function ProjectPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const router = useRouter();

  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [processingRuns, setProcessingRuns] = useState<
    Record<string, ProcessingRun[]>
  >({});
  const [processingRunsUnavailable, setProcessingRunsUnavailable] = useState<
    Record<string, boolean>
  >({});
  const [docsLoading, setDocsLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<UploadResponse | null>(
    null
  );
  const [dragOver, setDragOver] = useState(false);
  const [retryingVersion, setRetryingVersion] = useState<string | null>(null);
  const [processingActionError, setProcessingActionError] = useState<string | null>(null);
  const [oemSourceCount, setOemSourceCount] = useState(0);

  useEffect(() => {
    if (!projectId) return;
    void loadProject();
    void loadDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function loadProject() {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.fetchProject(projectId);
      setProject(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load project");
    } finally {
      setLoading(false);
    }
  }

  async function loadDocuments() {
    if (!projectId) return;
    setDocsLoading(true);
    setUploadError(null);
    try {
      const docs = await api.fetchDocuments(projectId);
      setDocuments(docs);
      const eligible = docs.filter((doc) =>
        ["failed", "partial"].includes(doc.processing_status)
      );
      const runResults: Array<readonly [string, ProcessingRun[], boolean]> =
        await Promise.all(
          eligible.map(async (doc) => {
            const key = `${doc.document_id}-${doc.version_number}`;
            try {
              return [
                key,
                await api.fetchProcessingRuns(
                  projectId,
                  doc.document_id,
                  doc.version_number
                ),
                false,
              ] as const;
            } catch {
              return [key, [] as ProcessingRun[], true] as const;
            }
          })
        );
      setProcessingRuns(Object.fromEntries(runResults.map(([key, runs]) => [key, runs])));
      setProcessingRunsUnavailable(
        Object.fromEntries(
          runResults.map(([key, _runs, unavailable]) => [key, unavailable])
        )
      );
    } catch (err) {
      setUploadError(
        err instanceof Error ? err.message : "Failed to load documents"
      );
    } finally {
      setDocsLoading(false);
    }
  }

  const isArchived = project?.status === "archived";
  const latestDocument = documents.length > 0 ? documents[documents.length - 1] : null;
  const latestDocumentReady = latestDocument
    ? ["parsed", "partial", "ocr_warning"].includes(latestDocument.processing_status)
    : false;
  const hasProcessingDocuments = documents.some((doc) =>
    ["uploaded", "queued", "processing"].includes(doc.processing_status)
  );

  useEffect(() => {
    if (!hasProcessingDocuments) return;
    const timer = window.setInterval(() => {
      void loadDocuments();
      void loadProject();
    }, 2500);
    return () => window.clearInterval(timer);
    // Poll only while a document is actively moving through the worker.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasProcessingDocuments, projectId]);

  async function handleRename() {
    if (!project || !draftName.trim() || saving) return;
    setSaving(true);
    try {
      const updated = await api.renameProject(project.id, {
        name: draftName.trim(),
      });
      setProject(updated);
      setEditingName(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to rename");
    } finally {
      setSaving(false);
    }
  }

  async function handleArchive() {
    if (!project) return;
    setActionLoading("archive");
    try {
      const updated = await api.archiveProject(project.id);
      setProject(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleReopen() {
    if (!project) return;
    setActionLoading("reopen");
    try {
      const updated = await api.reopenProject(project.id);
      setProject(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reopen");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleUpload(file: File) {
    if (!project || uploading) return;
    setUploading(true);
    setUploadError(null);
    setUploadSuccess(null);
    try {
      const result = await api.uploadDocument(project.id, file);
      setUploadSuccess(result);
      setProject((p) =>
        p ? { ...p, status: result.project_status } : p
      );
      void loadDocuments();
    } catch (err) {
      setUploadError(
        err instanceof Error ? err.message : "Upload failed"
      );
    } finally {
      setUploading(false);
    }
  }

  async function handleRetryProcessing(doc: DocumentItem) {
    if (!project || isArchived) return;
    const key = `${doc.document_id}-${doc.version_number}`;
    setRetryingVersion(key);
    setProcessingActionError(null);
    try {
      await api.retryDocumentProcessing(
        project.id,
        doc.document_id,
        doc.version_number
      );
      await Promise.all([loadDocuments(), loadProject()]);
    } catch (err) {
      setProcessingActionError(
        err instanceof Error ? err.message : "Could not retry document processing"
      );
    } finally {
      setRetryingVersion(null);
    }
  }

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        void handleUpload(file);
        // Reset the input so the same file can be re-selected if needed.
        e.target.value = "";
      }
    },
    [project, uploading]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setDragOver(false);
      if (uploading || !project || isArchived) return;
      const file = e.dataTransfer.files?.[0];
      if (file) {
        void handleUpload(file);
      }
    },
    [uploading, project, isArchived]
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      if (!uploading && project && !isArchived) {
        setDragOver(true);
      }
    },
    [uploading, project, isArchived]
  );

  const handleDragLeave = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setDragOver(false);
    },
    []
  );

  if (loading) {
    return (
      <AppShell>
        <div className="page-scroll">
          <div className="page-container">
            <div className="empty-state">
              <FileText size={32} aria-hidden="true" />
              <strong>Loading project…</strong>
            </div>
          </div>
        </div>
      </AppShell>
    );
  }

  if (error || !project) {
    return (
      <AppShell>
        <div className="page-scroll">
          <div className="page-container">
            <div className="empty-state">
              <FileText size={32} aria-hidden="true" />
              <strong>
                {error ?? "Project not found"}
              </strong>
              <Link
                href="/dashboard"
                className="button button-secondary button-small"
              >
                Back to projects
              </Link>
            </div>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      {/* ----- Topbar ----- */}
      <header className="project-topbar">
        <div className="project-breadcrumbs">
          <Link href="/dashboard" className="breadcrumb-back" aria-label="Back to projects">
            <ArrowLeft size={15} aria-hidden="true" />
          </Link>
          <span className="breadcrumb-muted">Projects</span>
          <span className="breadcrumb-separator">/</span>
          <strong>{project.name}</strong>
          <span className="project-id">{project.id}</span>
        </div>

        <div className="project-topbar-actions">
          {isArchived ? (
            <button
              className="button button-primary button-small"
              type="button"
              onClick={handleReopen}
              disabled={actionLoading === "reopen"}
            >
              {actionLoading === "reopen" ? "Reopening…" : "Reopen"}
            </button>
          ) : (
            <button
              className="button button-secondary button-small"
              type="button"
              onClick={handleArchive}
              disabled={actionLoading === "archive"}
            >
              {actionLoading === "archive" ? "Archiving…" : "Archive"}
            </button>
          )}
          {latestDocumentReady ? (
            <>
              <Link
                href={`/projects/${project.id}/review`}
                className="button button-secondary button-small"
              >
                Review requirements
              </Link>
              <Link
                href={`/projects/${project.id}/matrix`}
                className="button button-primary button-small"
              >
                Compliance sheet
              </Link>
            </>
          ) : null}
        </div>
      </header>

      <div className="page-scroll">
        <div className="page-container">
          <section className="page-heading">
            <div>
              <h1>{project.name}</h1>
              <p className="page-description">
                Add the tender and vendor/OEM sources, review the evidence-backed
                decisions, then export the final compliance sheet. Current status:
                {" "}{statusLabel(project.status)}.
              </p>
            </div>
          </section>

          <ProjectFlowNav
            projectId={project.id}
            current={latestDocumentReady ? "vendor" : "tender"}
            tenderReady={latestDocumentReady}
            vendorReady={oemSourceCount > 0}
          />

          {/* ----- Project details panel ----- */}
          <div className="detail-panel">
            <div className="detail-section">
              <h2 className="detail-section-title">Details</h2>

              <div className="detail-row">
                <span className="detail-label">Name</span>
                {editingName ? (
                  <div className="detail-row detail-row-editing">
                    <input
                      type="text"
                      aria-label="Project name"
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void handleRename();
                        if (e.key === "Escape") {
                          setEditingName(false);
                          setDraftName(project.name);
                        }
                      }}
                      disabled={saving}
                      autoFocus
                    />
                    <button
                      className="icon-button"
                      type="button"
                      onClick={async () => {
                        await handleRename();
                      }}
                      disabled={saving || !draftName.trim()}
                      aria-label="Save"
                    >
                      <Save size={14} aria-hidden="true" />
                    </button>
                    <button
                      className="icon-button"
                      type="button"
                      onClick={() => {
                        setEditingName(false);
                        setDraftName(project.name);
                      }}
                      disabled={saving}
                      aria-label="Cancel"
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className="detail-value">{project.name}</span>
                    <button
                      className="icon-button"
                      type="button"
                      onClick={() => {
                        setEditingName(true);
                        setDraftName(project.name);
                      }}
                      aria-label="Rename"
                    >
                      <Pencil size={14} aria-hidden="true" />
                    </button>
                  </div>
                )}
              </div>

              <div className="detail-row">
                <span className="detail-label">Status</span>
                <span className="detail-value">{statusLabel(project.status)}</span>
              </div>

              <div className="detail-row">
                <span className="detail-label">External tender ID</span>
                <span className="detail-value">
                  {project.external_tender_id ?? "—"}
                </span>
              </div>

              <div className="detail-row">
                <span className="detail-label">Created by</span>
                <span className="detail-value">
                  {project.created_by ?? "—"}
                </span>
              </div>

              <div className="detail-row">
                <span className="detail-label">Created</span>
                <span className="detail-value">
                  {formatDate(project.created_at)}
                </span>
              </div>

              <div className="detail-row">
                <span className="detail-label">Updated</span>
                <span className="detail-value">
                  {formatDate(project.updated_at)}
                </span>
              </div>
            </div>

            {/* ----- Upload section ----- */}
            <div className="upload-section source-section-anchor" id="tender-sources">
              <div className="source-section-heading">
                <div>
                  <p className="eyebrow">Step 1 · Tender</p>
                  <h2 className="detail-section-title">Tender documents</h2>
                  <p className="field-help">
                    Upload the tender, RFQ, or technical specification that defines
                    what the proposed product must meet.
                  </p>
                </div>
              </div>

              {uploadSuccess && (
                <div className="upload-success-banner">
                  <Check size={16} aria-hidden="true" />
                  <span>
                    Uploaded <strong>{uploadSuccess.filename}</strong>
                    — v{uploadSuccess.version_number} ·{" "}
                    {uploadSuccess.content_length} bytes · SHA-256:
                    {uploadSuccess.checksum_sha256.slice(0, 12)}…
                  </span>
                </div>
              )}

              {uploadError && (
                <div className="upload-error-banner">
                  <AlertCircle size={16} aria-hidden="true" />
                  <span>{uploadError}</span>
                </div>
              )}

              <div
                className={`upload-dropzone ${
                  dragOver ? "drag-over" : ""
                } ${isArchived ? "disabled" : ""}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <Upload size={32} className="upload-icon" aria-hidden="true" />
                <div className="upload-dropzone-text">
                  {uploading ? (
                    <strong>Uploading…</strong>
                  ) : isArchived ? (
                    <strong>Archived — cannot upload</strong>
                  ) : dragOver ? (
                    <strong>Drop to upload</strong>
                  ) : (
                    <>
                      <strong>Drag & drop the tender PDF or DOCX here</strong>
                      <span
                        style={{
                          fontSize: 12,
                          color: "var(--text-tertiary)",
                        }}
                      >
                        or use the file chooser below
                      </span>
                    </>
                  )}
                </div>
                <input
                  type="file"
                  accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={handleFileChange}
                  disabled={uploading || isArchived}
                  className="upload-input"
                  aria-label="Choose PDF or DOCX file"
                />
              </div>
            </div>

            {/* ----- Document list ----- */}
            <div className="doclist-section">
              <div className="section-title-row">
                <div>
                  <h2>Tender source versions</h2>
                  <p>
                    {hasProcessingDocuments
                      ? "Processing updates automatically."
                      : latestDocumentReady
                        ? "Latest tender is ready for review."
                        : documents.length > 0
                          ? "Check the latest processing result below."
                          : "Upload a tender to begin."}
                  </p>
                </div>
                <p>
                  {documents.length === 1
                    ? "1 document version"
                    : `${documents.length} document versions`}
                </p>
              </div>

              {processingActionError ? (
                <div className="upload-error-banner" role="alert">
                  <AlertCircle size={14} aria-hidden="true" />
                  {processingActionError}
                </div>
              ) : null}

              {docsLoading ? (
                <div className="empty-state">
                  <FileText size={24} aria-hidden="true" />
                  <strong>Loading documents…</strong>
                </div>
              ) : documents.length === 0 ? (
                <div className="empty-state">
                  <FileText size={24} aria-hidden="true" />
                  <strong>No documents uploaded yet.</strong>
                  <p
                    style={{
                      marginTop: 4,
                      fontSize: 12,
                      color: "var(--text-tertiary)",
                    }}
                  >
                    Upload a tender to get started.
                  </p>
                </div>
              ) : (
                <table className="doclist-table">
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Version</th>
                      <th>Size</th>
                      <th>Status</th>
                      <th>Uploaded</th>
                      <th>Next step</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map((doc) => {
                      const processing = documentProcessingMeta(doc.processing_status);
                      const retryKey = `${doc.document_id}-${doc.version_number}`;
                      const canRetry = ["failed", "partial"].includes(doc.processing_status);
                      const isReady = ["parsed", "partial", "ocr_warning"].includes(
                        doc.processing_status
                      );

                      return (
                        <tr key={retryKey}>
                          <td>
                            <File size={14} aria-hidden="true" />
                            {doc.display_name}
                          </td>
                          <td>v{doc.version_number}</td>
                          <td>{formatBytes(doc.size_bytes)}</td>
                          <td>
                            <span className={`status-pill ${processing.className}`}>
                              {processing.label}
                            </span>
                            <div className="field-help">{processing.help}</div>
                          </td>
                          <td>{formatDate(doc.created_at)}</td>
                          <td>
                            {canRetry && (
                              <details className="processing-history">
                                <summary>Processing history</summary>
                                {processingRunsUnavailable[retryKey] ? (
                                  <p className="field-help">Processing history is temporarily unavailable.</p>
                                ) : (processingRuns[retryKey] ?? []).length === 0 ? (
                                  <p className="field-help">No stage attempts are recorded yet.</p>
                                ) : (
                                  <ol>
                                    {(processingRuns[retryKey] ?? []).slice(0, 8).map((run) => (
                                      <li key={run.id}>
                                        {processingStageLabel(run.stage)} — {processingStatusLabel(run.status)} (attempt {run.attempt})
                                        <span className="field-help">
                                          {formatDate(run.started_at)}
                                        </span>
                                      </li>
                                    ))}
                                  </ol>
                                )}
                                <p className="field-help">
                                  Retry reprocesses this same immutable upload.
                                  Error details are kept out of this view.
                                </p>
                              </details>
                            )}
                            {canRetry ? (
                              <button
                                className="button button-secondary button-small"
                                type="button"
                                disabled={retryingVersion !== null || isArchived}
                                onClick={() => void handleRetryProcessing(doc)}
                              >
                                <RefreshCw
                                  size={12}
                                  aria-hidden="true"
                                />
                                {retryingVersion === retryKey ? "Retrying…" : "Retry processing"}
                              </button>
                            ) : isReady ? (
                              <Link
                                href={`/projects/${project.id}/review`}
                                className="button button-secondary button-small"
                              >
                                Review requirements
                              </Link>
                            ) : (
                              <span className="field-help">Updates automatically</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}

              {documents.length > 0 && (
                <button
                  className="button button-secondary button-small"
                  type="button"
                  onClick={() => void loadDocuments()}
                  disabled={docsLoading}
                  style={{ marginTop: 12 }}
                >
                  <RefreshCw size={12} aria-hidden="true" />
                  Refresh
                </button>
              )}
            </div>

            {/* ----- OEM/vendor evidence sources ----- */}
            <OemDocumentsPanel
              projectId={project.id}
              disabled={isArchived}
              onItemsChange={(items) =>
                setOemSourceCount(
                  items.filter((item) =>
                    ["parsed", "partial", "ocr_warning"].includes(
                      item.processing_status
                    )
                  ).length
                )
              }
            />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
