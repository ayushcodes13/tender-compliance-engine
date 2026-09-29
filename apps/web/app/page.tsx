import { AppShell } from "@/components/app-shell";
import {
  ArrowRight,
  CircleCheck,
  FilePlus2,
  FileText,
  MoreHorizontal,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";

const projects = [
  {
    name: "Railway signalling system",
    tenderId: "TND-2026-0142",
    documents: 3,
    requirements: 38,
    review: 7,
    updated: "12 min ago",
    href: "/projects/demo",
  },
  {
    name: "Laboratory measurement platform",
    tenderId: "TND-2026-0136",
    documents: 2,
    requirements: 64,
    review: 0,
    updated: "Yesterday",
    href: "/projects/demo",
  },
];

export default function Home() {
  return (
    <AppShell>
      <header className="topbar">
        <div>
          <p className="topbar-kicker">Tender Compliance Engine</p>
          <p className="topbar-context">Phase 1 · Requirement extraction and review</p>
        </div>
        <button className="button button-primary" type="button">
          <FilePlus2 size={15} aria-hidden="true" />
          New tender
        </button>
      </header>

      <div className="page-scroll">
        <div className="page-container">
          <section className="page-heading">
            <div>
              <p className="eyebrow">Workspace</p>
              <h1 className="display-heading">Tender projects</h1>
              <p className="page-description">
                Turn technical tender documents into source-linked requirements before any compliance decision is made.
              </p>
            </div>
          </section>

          <section className="summary-strip" aria-label="Project summary">
            <div className="summary-item">
              <span className="summary-value">2</span>
              <span className="summary-label">Active tenders</span>
            </div>
            <div className="summary-item">
              <span className="summary-value">102</span>
              <span className="summary-label">Requirements extracted</span>
            </div>
            <div className="summary-item">
              <span className="summary-value summary-warning">7</span>
              <span className="summary-label">Need review</span>
            </div>
            <div className="summary-item">
              <span className="summary-value summary-success">95</span>
              <span className="summary-label">Reviewed</span>
            </div>
          </section>

          <div className="section-title-row">
            <div>
              <h2>Recent projects</h2>
              <p>Demo data for the frontend foundation.</p>
            </div>
          </div>

          <div className="project-grid">
            <button className="new-project-card" type="button">
              <span className="new-project-icon">
                <FilePlus2 size={20} aria-hidden="true" />
              </span>
              <span>
                <strong>Create tender project</strong>
                <small>Upload PDF or DOCX documents</small>
              </span>
            </button>

            {projects.map((project) => (
              <Link key={project.tenderId} href={project.href} className="project-card">
                <div className="project-card-top">
                  <span className="document-glyph">
                    <FileText size={18} strokeWidth={1.8} aria-hidden="true" />
                  </span>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={"More options for " + project.name}
                    onClick={(event) => event.preventDefault()}
                  >
                    <MoreHorizontal size={17} aria-hidden="true" />
                  </button>
                </div>

                <div className="project-card-copy">
                  <h3>{project.name}</h3>
                  <p>{project.tenderId}</p>
                </div>

                <div className="project-metrics">
                  <span>{project.documents} documents</span>
                  <span>{project.requirements} requirements</span>
                </div>

                <div className="project-card-footer">
                  <span className={project.review ? "status-pill status-warning" : "status-pill status-reviewed"}>
                    {project.review ? (
                      <TriangleAlert size={12} aria-hidden="true" />
                    ) : (
                      <CircleCheck size={12} aria-hidden="true" />
                    )}
                    {project.review ? project.review + " need review" : "Review complete"}
                  </span>
                  <span className="project-updated">{project.updated}</span>
                  <ArrowRight size={15} aria-hidden="true" />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
