"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, AlertCircle } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { FinalMatrixView } from "@/components/final-matrix-view";
import { ProjectFlowNav } from "@/components/project-flow-nav";
import { api, DocumentItem, Project } from "@/lib/api/client";

export default function ProjectMatrixPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const [project, setProject] = useState<Project | null>(null);
  const [document, setDocument] = useState<DocumentItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;

    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const [proj, docs] = await Promise.all([
          api.fetchProject(projectId),
          api.fetchDocuments(projectId),
        ]);
        setProject(proj);
        // Pick the latest version with a parsed status; fall back to newest.
        const parsed = docs
          .filter((d) => d.processing_status === "parsed")
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime()
          );
        const target =
          parsed.length > 0 ? parsed[0] : docs[docs.length - 1];
        if (!target) {
          setError(
            "No documents uploaded yet. Upload a document from the project page."
          );
          return;
        }
        setDocument(target);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load project"
        );
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId]);

  if (loading) {
    return (
      <AppShell>
        <div style={{ padding: "48px" }}>
          <p>Loading project…</p>
        </div>
      </AppShell>
    );
  }

  if (error || !project || !document) {
    return (
      <AppShell>
        <div style={{ padding: "48px" }}>
          <Link href="/dashboard" className="breadcrumb-back" aria-label="Back to projects">
            <ArrowLeft size={15} aria-hidden="true" />
          </Link>
          <div className="empty-list" style={{ marginTop: "24px" }}>
            <AlertCircle size={18} aria-hidden="true" />
            <strong>
              {error ?? "No tender available for the OEM response sheet"}
            </strong>
            {error ? <span>{error}</span> : null}
            <Link
              href={`/projects/${projectId}`}
              className="button button-secondary"
            >
              Back to project
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <header className="project-topbar">
        <div className="project-breadcrumbs">
          <Link href="/dashboard" className="breadcrumb-back" aria-label="Back to projects">
            <ArrowLeft size={15} aria-hidden="true" />
          </Link>
          <span className="breadcrumb-muted">Projects</span>
          <span className="breadcrumb-separator">/</span>
          <strong>{project.name}</strong>
        </div>

        <nav className="topnav-tabs" style={{ display: "flex", gap: 4 }}>
          <Link
            href={`/projects/${projectId}/review`}
            className="topnav-tab button button-secondary button-small"
          >
            Review
          </Link>
          <Link
            href={`/projects/${projectId}/matrix`}
            className="topnav-tab button button-primary button-small"
            style={{ fontWeight: 600 }}
          >
            OEM response sheet
          </Link>
        </nav>
      </header>

      <div className="page-scroll">
        <div className="page-container">
          <section className="page-heading">
            <div>
            <h1>OEM response sheet — {project.name}</h1>
              <p className="page-description">
                Review the tender’s technical specifications and create a source-linked
                response sheet with blank OEM fields. The system does not decide compliance.
                Tender source:
                {" "}v{document.version_number} · {document.display_name}
              </p>
            </div>
          </section>

          <ProjectFlowNav
            projectId={projectId}
            current="response"
            tenderReady
            documentId={document.document_id}
            version={document.version_number}
          />

          <FinalMatrixView
            projectId={projectId}
            documentId={document.document_id}
            version={document.version_number}
            documentName={document.display_name}
            technicalOnly
          />
        </div>
      </div>
    </AppShell>
  );
}
