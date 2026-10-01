"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  ArrowLeft,
  FileText,
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
import {
  api,
  Project,
  DocumentItem,
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
      return "Matrix ready";
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
  const [docsLoading, setDocsLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<UploadResponse | null>(
    null
  );
  const [dragOver, setDragOver] = useState(false);

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
    } catch (err) {
      setUploadError(
        err instanceof Error ? err.message : "Failed to load documents"
      );
    } finally {
      setDocsLoading(false);
    }
  }

  const isArchived = project?.status === "archived";

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

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        void handleUpload(file);
        // Reset the input so the same file can be re-selected if needed.
        e.target.value = "";
      }
    },
    [uploading]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setDragOver(false);
      if (uploading || !project) return;
      const file = e.dataTransfer.files?.[0];
      if (file) {
        void handleUpload(file);
      }
    },
    [uploading]
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
                href="/"
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
          <Link href="/" className="breadcrumb-back" aria-label="Back to projects">
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
          <Link
            href={`/projects/${project.id}/review`}
            className="icon-button"
            aria-label="Open review workspace"
            style={{ display: "none" }}
          >
            {/* Review workspace will be wired in a later checkpoint */}
          </Link>
        </div>
      </header>

      <div className="page-scroll">
        <div className="page-container">
          <section className="page-heading">
            <div>
              <p className="eyebrow">Project</p>
              <h1 className="display-heading">{project.name}</h1>
              <p className="page-description">
                Workflow status: {statusLabel(project.status)}.
              </p>
            </div>
          </section>

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
                      ✏️
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
            <div className="upload-section">
              <h2 className="detail-section-title">Upload documents</h2>

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
                      <strong>Drag & drop a PDF here</strong>
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
                  accept="application/pdf"
                  onChange={handleFileChange}
                  disabled={uploading || isArchived}
                  className="upload-input"
                  aria-label="Choose PDF file"
                />
              </div>
            </div>

            {/* ----- Document list ----- */}
            <div className="doclist-section">
              <div className="section-title-row">
                <h2>Documents</h2>
                <p>
                  {documents.length === 1
                    ? "1 document version"
                    : `${documents.length} document versions`}
                </p>
              </div>

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
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map((doc) => (
                      <tr key={`${doc.document_id}-${doc.version_number}`}>
                        <td>
                          <File size={14} aria-hidden="true" />
                          {doc.display_name}
                        </td>
                        <td>v{doc.version_number}</td>
                        <td>{formatBytes(doc.size_bytes)}</td>
                        <td>{doc.processing_status}</td>
                        <td>{formatDate(doc.created_at)}</td>
                      </tr>
                    ))}
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
          </div>
        </div>
      </div>
    </AppShell>
  );
}
