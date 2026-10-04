"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { FilePlus2, FileText, MoreHorizontal } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { api, Project } from "@/lib/api/client";

/* eslint-disable unicorn/prefer-string-starts-ends-with -- status is a known enum */

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
  return new Date(date).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

const activeStatusPills: Record<Project["status"], string> = {
  draft: "status-pill status-neutral",
  tender_uploaded: "status-pill status-neutral",
  documents_processing: "status-pill status-neutral",
  requirements_extracted: "status-pill status-neutral",
  review_in_progress: "status-pill status-warning",
  matrix_ready: "status-pill status-reviewed",
  exported: "status-pill status-reviewed",
  archived: "status-pill status-warning",
};

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDialog, setShowDialog] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const router = useRouter();

  const loadProjects = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.fetchProjects();
      setProjects(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadProjects();
  }, []);

  const activeProjects = projects.filter((p) => p.status !== "archived");
  const archivedProjects = projects.filter((p) => p.status === "archived");
  const inReviewProjects = projects.filter((p) => p.status === "review_in_progress");
  const readyProjects = projects.filter(
    (p) => p.status === "matrix_ready" || p.status === "exported"
  );

  const openDialog = () => {
    setNewName("");
    setShowDialog(true);
  };

  const closeDialog = () => {
    if (creating) return;
    setShowDialog(false);
    setNewName("");
  };

  const handleCreate = async () => {
    if (!newName.trim() || creating) return;
    setCreating(true);
    try {
      const project = await api.createProject({ name: newName.trim() });
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setCreating(false);
      setShowDialog(false);
      setNewName("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !creating && newName.trim()) {
      void handleCreate();
    }
    if (e.key === "Escape") {
      closeDialog();
    }
  };

  /* ---- Project card (shared by active + archived) ---- */

  function ProjectCard({ project }: { project: Project }) {
    const isArchived = project.status === "archived";
    return (
      <Link
        key={project.id}
        href={`/projects/${project.id}`}
        className={
          "project-card" + (isArchived ? " project-card-archived" : "")
        }
      >
        <div className="project-card-top">
          <span className="document-glyph">
            <FileText size={18} strokeWidth={1.8} aria-hidden="true" />
          </span>
          <span className="icon-button" aria-hidden="true">
            <MoreHorizontal size={17} />
          </span>
        </div>

        <div className="project-card-copy">
          <h3>{project.name}</h3>
          {project.external_tender_id ? (
            <p>{project.external_tender_id}</p>
          ) : null}
        </div>

        <div className="project-card-footer">
          <span className={activeStatusPills[project.status]}>
            {statusLabel(project.status)}
          </span>
          <span className="project-updated">{formatDate(project.updated_at)}</span>
          <FilePlus2 size={15} aria-hidden="true" />
        </div>
      </Link>
    );
  }

  return (
    <AppShell>
      {/* ----- Topbar ----- */}
      <header className="topbar">
        <div>
          <p className="topbar-kicker">Tender Compliance Engine</p>
          <p className="topbar-context">
            Tender → OEM evidence → Compliance
          </p>
        </div>
        <button
          className="button button-primary"
          type="button"
          onClick={openDialog}
        >
          <FilePlus2 size={15} aria-hidden="true" />
          New tender
        </button>
      </header>

      <div className="page-scroll">
        <div className="page-container">
          {/* ----- Hero ----- */}
          {!loading && !error && projects.length === 0 && (
            <section className="hero">
              <h1>
                Tender&nbsp;compliance,<br />
                <span className="curve-text">simplified.</span>
              </h1>
              <p className="subtitle">
                Upload a tender, verify its requirements, attach OEM evidence,
                review compliance, and export the final submission.
              </p>
              <div className="hero-actions">
                <button
                  className="button button-primary"
                  type="button"
                  onClick={openDialog}
                >
                  <FilePlus2 size={15} aria-hidden="true" />
                  Create your first tender
                </button>
              </div>
              <div className="hero-meta">
                <span>No credit card required</span>
                <span aria-hidden="true">·</span>
                <span>Self-hosted</span>
              </div>
            </section>
          )}

          {/* ----- Heading (when projects exist) ----- */}
          {!loading && !error && projects.length > 0 && (
            <section className="page-heading">
              <div>
                <h1>Projects</h1>
                <p className="page-description">
                  Upload a tender, verify its requirements, attach OEM evidence,
                  review compliance, and export the final submission.
                </p>
              </div>
            </section>
          )}

          {/* ----- Summary line ----- */}
          <p className="summary-inline">
            {loading
              ? "Loading…"
              : error
                ? "Error"
                : projects.length === 0
                  ? "No projects yet"
                  : `${projects.length} total project${projects.length === 1 ? "" : "s"}`}
          </p>

          {/* ----- Loading ----- */}
          {loading && (
            <div className="empty-state">
              <FileText size={32} aria-hidden="true" />
              <strong>Loading projects…</strong>
            </div>
          )}

          {/* ----- Error ----- */}
          {error && !loading && (
            <div className="empty-state">
              <FileText size={32} aria-hidden="true" />
              <strong>{error}</strong>
              <button
                className="button button-secondary button-small"
                onClick={loadProjects}
              >
                Retry
              </button>
            </div>
          )}

          {/* ----- Empty ----- */}
          {!loading && !error && projects.length === 0 && (
            <div className="empty-state">
              <FileText size={32} aria-hidden="true" />
              <strong>No projects yet</strong>
              <p>Create a tender project to get started.</p>
            </div>
          )}

          {/* ----- Project grid ----- */}
          {!loading && !error && projects.length > 0 && (
            <div className="project-grid">
              <button
                className="new-project-card"
                type="button"
                onClick={openDialog}
              >
                <span className="new-project-icon">
                  <FilePlus2 size={20} aria-hidden="true" />
                </span>
                <span>
                  <strong>Create tender project</strong>
                  <small>Upload PDF or DOCX documents</small>
                </span>
              </button>

              {activeProjects.map((project) => (
                <ProjectCard key={project.id} project={project} />
              ))}

              {archivedProjects.length > 0 && (
                <>
                  <div className="section-title-row" style={{ marginTop: 32 }}>
                    <h2>Archived</h2>
                  </div>
                  {archivedProjects.map((project) => (
                    <ProjectCard key={project.id} project={project} />
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ----- New project dialog ----- */}
      {showDialog && (
        <div
          className="dialog-overlay"
          onClick={closeDialog}
          role="dialog"
          aria-modal="true"
          aria-label="New tender project"
        >
          <div
            className="dialog"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <h3>New tender project</h3>
            <input
              type="text"
              placeholder="Project name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={creating}
              autoFocus
            />
            <div className="dialog-actions">
              <button
                className="button button-secondary button-small"
                type="button"
                onClick={closeDialog}
                disabled={creating}
              >
                Cancel
              </button>
              <button
                className="button button-primary button-small"
                type="button"
                onClick={handleCreate}
                disabled={creating || !newName.trim()}
              >
                {creating ? "Creating…" : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
