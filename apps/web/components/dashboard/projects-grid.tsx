"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Archive,
  Check,
  ChevronDown,
  FilePlus2,
  FileText,
  Plus,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

import { api, Project } from "@/lib/api/client";

const statusConfig: Record<
  Project["status"],
  { label: string; className: string; icon: "check" | "processing" | "file" }
> = {
  draft: { label: "Draft", className: "status-neutral", icon: "file" },
  tender_uploaded: { label: "Tender uploaded", className: "status-neutral", icon: "file" },
  documents_processing: { label: "Processing", className: "status-warning", icon: "processing" },
  requirements_extracted: { label: "Requirements extracted", className: "status-neutral", icon: "file" },
  review_in_progress: { label: "Review in progress", className: "status-warning", icon: "processing" },
  matrix_ready: { label: "Matrix ready", className: "status-reviewed", icon: "check" },
  exported: { label: "Exported", className: "status-reviewed", icon: "check" },
  archived: { label: "Archived", className: "status-neutral", icon: "file" },
};

function formatDate(date: string): string {
  const value = new Date(date);
  if (Number.isNaN(value.getTime())) return "Recently";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: value.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  }).format(value);
}

export function ProjectsGrid() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDialog, setShowDialog] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");
  const router = useRouter();

  const dialogRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  const loadProjects = useCallback(async () => {
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
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const activeProjects = useMemo(() => projects
    .filter((project) => project.status !== "archived")
    .filter((project) => matchesQuery(project, query))
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)), [projects, query]);
  const archivedProjects = useMemo(() => projects
    .filter((project) => project.status === "archived")
    .filter((project) => matchesQuery(project, query))
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)), [projects, query]);
  const inProgressCount = projects.filter((project) =>
    project.status === "documents_processing" || project.status === "review_in_progress",
  ).length;
  const readyCount = projects.filter((project) =>
    project.status === "matrix_ready" || project.status === "exported",
  ).length;

  const openDialog = () => {
    restoreFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    setNewName("");
    setShowDialog(true);
  };

  const closeDialog = () => {
    if (creating) return;
    setShowDialog(false);
    setNewName("");
  };

  useEffect(() => {
    if (!showDialog) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!creating) closeDialog();
        return;
      }
      if (event.key !== "Tab") return;
      const root = dialogRef.current;
      if (!root) return;
      const focusable = Array.from(root.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )).filter((element) => element.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !root.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [showDialog, creating]);

  useEffect(() => {
    if (showDialog || !restoreFocusRef.current) return;
    const target = restoreFocusRef.current;
    restoreFocusRef.current = null;
    if (target.isConnected) target.focus();
  }, [showDialog]);

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

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !creating && newName.trim()) void handleCreate();
  };

  return (
    <>
      <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.13em] text-text-tertiary">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            Tender workspace
          </div>
          <h1 className="font-display text-[2rem] font-bold leading-tight tracking-[-0.035em] text-text-primary">
            Your tenders
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
            Keep each tender, its source documents, review, and export together.
          </p>
        </div>
        <motion.button
          className="inline-flex min-h-11 items-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-accent-hover active:scale-[0.96] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
          onClick={openDialog}
          whileTap={{ scale: 0.96 }}
        >
          <Plus className="h-4 w-4" strokeWidth={2} />
          New tender
        </motion.button>
      </header>

      <section className="mb-6 grid overflow-hidden rounded-xl border border-border bg-surface shadow-sm sm:grid-cols-[minmax(0,1fr)_auto]" aria-label="Workspace overview">
        <div className="relative flex min-h-[142px] flex-col justify-center px-6 py-5 sm:px-7">
          <div className="absolute inset-y-5 left-0 w-[3px] rounded-r bg-accent" />
          <p className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">Your workspace</p>
          <p className="mt-1 text-lg font-semibold tracking-tight text-text-primary">
            {projects.length === 0 ? "Start with a tender" : `${projects.length} ${projects.length === 1 ? "project" : "projects"} in your workspace`}
          </p>
          <p className="mt-1 max-w-xl text-sm text-text-secondary">
            {projects.length === 0
              ? "Create a project to upload a tender and start a source-linked review."
              : "Continue a tender review or start with another tender."}
          </p>
        </div>
        <div className="grid grid-cols-2 border-t border-border sm:border-l sm:border-t-0">
          <OverviewStat label="In progress" value={inProgressCount} hint="Processing or review" />
          <OverviewStat label="Ready" value={readyCount} hint="Matrix or exported" />
        </div>
      </section>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-text-primary">Your tenders</h2>
          <p className="mt-0.5 text-xs text-text-tertiary">Sorted by most recently updated</p>
        </div>
        {projects.length > 0 && (
          <label className="relative block w-full sm:w-64">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary" aria-hidden="true" />
            <input
              type="search"
              aria-label="Search tenders"
              placeholder="Search tenders…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="h-10 w-full rounded-md border border-border bg-surface pl-9 pr-3 text-sm text-text-primary placeholder:text-text-tertiary transition-colors focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15"
            />
          </label>
        )}
      </div>

      {loading && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Loading projects" aria-busy="true">
          {[...Array(4)].map((_, index) => (
            <div key={index} className="h-44 animate-pulse rounded-xl border border-border bg-surface p-5">
              <div className="h-9 w-9 rounded-lg bg-background" />
              <div className="mt-5 h-4 w-2/3 rounded bg-background" />
              <div className="mt-2 h-3 w-1/3 rounded bg-background" />
              <div className="mt-6 h-3 w-full rounded bg-background" />
            </div>
          ))}
        </div>
      )}

      {error && !loading && (
        <div className="flex items-center gap-3 rounded-lg border border-error/20 bg-error-bg p-4 text-sm text-error" role="alert">
          <FileText className="h-4 w-4 shrink-0" />
          <span>{error}</span>
          <button className="ml-auto inline-flex min-h-10 items-center gap-1 rounded px-2 font-medium underline-offset-2 hover:underline" onClick={() => void loadProjects()}>
            <RefreshCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      )}

      {!loading && !error && projects.length === 0 && (
        <div className="flex min-h-[230px] flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface px-6 py-10 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent-soft text-accent">
            <FilePlus2 className="h-5 w-5" strokeWidth={1.8} />
          </div>
          <h3 className="mt-4 font-semibold text-text-primary">Your first tender starts here</h3>
          <p className="mt-1 max-w-sm text-sm text-text-secondary">
            Create a project, upload the tender, then review every extracted requirement against its source.
          </p>
          <button className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-hover active:scale-[0.96]" onClick={openDialog}>
            <Plus className="h-4 w-4" /> Create project
          </button>
        </div>
      )}

      {!loading && !error && projects.length > 0 && (
        <div className="space-y-5">
          {activeProjects.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {activeProjects.map((project, index) => (
                <ProjectCard key={project.id} project={project} index={index} />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-border bg-surface px-5 py-10 text-center">
              <Search className="mx-auto h-5 w-5 text-text-tertiary" />
              <p className="mt-3 text-sm font-medium text-text-primary">No active tenders match “{query}”</p>
              <button className="mt-2 text-sm font-medium text-accent hover:underline" onClick={() => setQuery("")}>Clear search</button>
            </div>
          )}

          {archivedProjects.length > 0 && (
            <details className="group overflow-hidden rounded-lg border border-border bg-surface" open={false}>
              <summary className="flex min-h-12 cursor-pointer list-none items-center gap-2 px-4 text-sm text-text-secondary transition-colors hover:bg-surface-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent [&::-webkit-details-marker]:hidden">
                <ChevronDown className="h-4 w-4 text-text-tertiary transition-transform duration-150 group-open:rotate-180" aria-hidden="true" />
                <Archive className="h-4 w-4" aria-hidden="true" />
                <span className="font-medium text-text-primary">Archived</span>
                <span className="rounded-full bg-background px-2 py-0.5 text-xs tabular-nums">{archivedProjects.length}</span>
                <span className="ml-auto text-xs text-text-tertiary">Show archived tenders</span>
              </summary>
              <div className="grid gap-3 border-t border-border bg-background/60 p-3 sm:grid-cols-2 xl:grid-cols-3">
                {archivedProjects.map((project, index) => (
                  <ProjectCard key={project.id} project={project} index={index} />
                ))}
              </div>
            </details>
          )}
          {activeProjects.length === 0 && archivedProjects.length === 0 && (
            <div className="rounded-xl border border-border bg-surface px-5 py-10 text-center">
              <Search className="mx-auto h-5 w-5 text-text-tertiary" />
              <p className="mt-3 text-sm font-medium text-text-primary">No tenders match “{query}”</p>
              <button className="mt-2 text-sm font-medium text-accent hover:underline" onClick={() => setQuery("")}>Clear search</button>
            </div>
          )}
        </div>
      )}

      <AnimatePresence initial={false}>
        {showDialog && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center bg-[#172033]/35 p-4 backdrop-blur-[2px]"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={closeDialog}
          >
            <motion.div
              className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-xl"
              role="dialog" aria-modal="true" aria-labelledby="create-project-title"
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.16, ease: "easeOut" }}
              onClick={(event) => event.stopPropagation()} ref={dialogRef}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 id="create-project-title" className="text-lg font-semibold text-text-primary">New tender project</h3>
                  <p className="mt-1 text-sm text-text-secondary">Give this bid a name you can find later.</p>
                </div>
                <button className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-text-tertiary hover:bg-background hover:text-text-primary" onClick={closeDialog} aria-label="Close dialog" disabled={creating}>
                  <X className="h-4 w-4" />
                </button>
              </div>
              <label htmlFor="project-name" className="mt-5 block text-xs font-semibold text-text-secondary">Project name</label>
              <input
                id="project-name" type="text" placeholder="e.g. Hospital imaging tender 2026"
                value={newName} onChange={(event) => setNewName(event.target.value)} onKeyDown={handleKeyDown}
                disabled={creating} autoFocus
                className="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15"
              />
              <div className="mt-6 flex justify-end gap-2">
                <button className="min-h-10 rounded-md px-4 text-sm font-medium text-text-secondary hover:bg-background hover:text-text-primary" onClick={closeDialog} disabled={creating}>Cancel</button>
                <button className="inline-flex min-h-10 items-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50" onClick={() => void handleCreate()} disabled={creating || !newName.trim()}>
                  {creating ? "Creating…" : "Create project"}
                  {!creating && <ArrowRight className="h-4 w-4" />}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function matchesQuery(project: Project, query: string): boolean {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return true;
  return project.name.toLocaleLowerCase().includes(normalized)
    || (project.external_tender_id ?? "").toLocaleLowerCase().includes(normalized);
}

function OverviewStat({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="flex min-w-[112px] flex-col justify-center px-5 py-4 sm:px-6">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">{label}</span>
      <span className="mt-1 text-2xl font-semibold leading-none tabular-nums tracking-tight text-text-primary">{value}</span>
      <span className="mt-1.5 text-[11px] text-text-tertiary">{hint}</span>
    </div>
  );
}

function ProjectCard({ project, index }: { project: Project; index: number }) {
  const config = statusConfig[project.status];
  const isArchived = project.status === "archived";
  const StatusIcon = config.icon === "check" ? Check : config.icon === "processing" ? RefreshCw : FileText;

  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, delay: Math.min(index, 5) * 0.025, ease: "easeOut" }}
      className={cn(
        "group relative flex min-h-[178px] flex-col rounded-xl border bg-surface transition-[border-color,box-shadow,background-color] duration-150",
        isArchived ? "border-border opacity-75" : "border-border hover:border-border-hover hover:bg-white hover:shadow-md",
      )}
    >
      <Link href={`/projects/${project.id}`} className="flex flex-1 flex-col rounded-xl p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg", isArchived ? "bg-background text-text-tertiary" : "bg-accent-soft text-accent")}>
            <FileText className="h-[18px] w-[18px]" strokeWidth={1.8} />
          </div>
          <span className={cn("status-pill inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium", config.className)}>
            <StatusIcon className="h-3 w-3" strokeWidth={2} />
            {config.label}
          </span>
        </div>
        <h3 className="mt-4 line-clamp-2 min-h-[1.5rem] break-words text-[15px] font-semibold leading-5 text-text-primary group-hover:text-accent">
          {project.name}
        </h3>
        <p className="mt-1 truncate text-xs text-text-tertiary">
          {project.external_tender_id || "Tender project"}
        </p>
        <div className="mt-auto flex items-center justify-between gap-3 border-t border-border/80 pt-3 text-xs text-text-tertiary">
          <span>Updated <time dateTime={project.updated_at}>{formatDate(project.updated_at)}</time></span>
          <span className="inline-flex items-center gap-1 font-medium text-text-secondary transition-colors group-hover:text-accent">
            Open <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
          </span>
        </div>
      </Link>
    </motion.div>
  );
}
