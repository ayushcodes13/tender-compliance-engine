"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { ArrowLeft, FileText, Save, X } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { api, Project } from "@/lib/api/client";

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

  useEffect(() => {
    void loadProject();
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

  const isArchived = project?.status === "archived";

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

            {/* ----- Document / requirement counts placeholder ----- */}
            <div className="detail-section">
              <h2 className="detail-section-title">Contents</h2>
              <div className="detail-row">
                <span className="detail-label">Documents</span>
                <span className="detail-value">Not available yet</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Requirements</span>
                <span className="detail-value">Not available yet</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
