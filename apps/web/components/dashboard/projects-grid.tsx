"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  FilePlus2,
  FileText,
  MoreHorizontal,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

import { api, Project } from "@/lib/api/client";

const statusConfig: Record<
  Project["status"],
  { label: string; className: string }
> = {
  draft: { label: "Draft", className: "status-neutral" },
  tender_uploaded: { label: "Tender uploaded", className: "status-neutral" },
  documents_processing: { label: "Processing", className: "status-warning" },
  requirements_extracted: { label: "Extracted", className: "status-neutral" },
  review_in_progress: { label: "In review", className: "status-warning" },
  matrix_ready: { label: "Matrix ready", className: "status-reviewed" },
  exported: { label: "Exported", className: "status-reviewed" },
  archived: { label: "Archived", className: "status-warning" },
};

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export function ProjectsGrid() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDialog, setShowDialog] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
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
      setError(
        err instanceof Error ? err.message : "Failed to load projects"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const activeProjects = projects.filter((p) => p.status !== "archived");
  const archivedProjects = projects.filter((p) => p.status === "archived");

  const openDialog = () => {
    // Remember whatever had focus so it can be handed back on close.
    restoreFocusRef.current =
      document.activeElement instanceof HTMLElement
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

  // Escape closes the dialog from anywhere inside it, and Tab is trapped
  // within it. Registered on the document because the backdrop is a sibling of
  // the dialog panel, so focus never sits on the element that would need the
  // handler attached to it.
  useEffect(() => {
    if (!showDialog) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!creating) closeDialog();
        return;
      }

      // Trap Tab inside the dialog. Without this, tabbing walks out into the
      // page behind the modal and keyboard users lose their place.
      if (event.key !== "Tab") return;
      const root = dialogRef.current;
      if (!root) return;

      const focusable = Array.from(
        root.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => el.offsetParent !== null);
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && (active === first || !root.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [showDialog, creating]);

  // Return focus to the control that opened the dialog, so dismissing it does
  // not drop the user back at the top of the document.
  useEffect(() => {
    if (showDialog) return;
    const target = restoreFocusRef.current;
    if (!target) return;
    restoreFocusRef.current = null;
    // The trigger can unmount while the dialog is open, so check it is still in
    // the document before handing focus back.
    if (target.isConnected) target.focus();
  }, [showDialog]);

  const handleCreate = async () => {
    if (!newName.trim() || creating) return;
    setCreating(true);
    try {
      const project = await api.createProject({ name: newName.trim() });
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create project"
      );
    } finally {
      setCreating(false);
      setShowDialog(false);
      setNewName("");
    }
  };

  // Enter submits. Escape is handled by the dialog-level listener so it works
  // from anywhere inside the dialog, not just this field.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !creating && newName.trim()) {
      void handleCreate();
    }
  };

  return (
    <>
      {/* Projects header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-text-primary">
            Projects
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            Upload a tender, verify requirements, attach OEM evidence, review
            compliance, and export the final submission.
          </p>
        </div>
        <motion.button
          className={cn(
            "flex items-center gap-2 rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-white",
            "hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent",
          )}
          onClick={openDialog}
          whileHover={{ y: -1 }}
          transition={{ duration: 0.15, ease: "easeOut" }}
        >
          <Plus className="h-4 w-4" />
          New tender
        </motion.button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-40 animate-pulse rounded-xl border border-border bg-surface"
            />
          ))}
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="flex items-center gap-3 rounded-lg border border-error/20 bg-error-bg p-4 text-sm text-error">
          <FileText className="h-4 w-4 shrink-0" />
          <span>{error}</span>
          <button
            className="ml-auto text-sm underline"
            onClick={() => void loadProjects()}
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && projects.length === 0 && (
        <motion.div
          className="flex min-h-[300px] flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface p-8 text-center"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <FileText className="h-12 w-12 text-text-tertiary" />
          <p className="mt-3 font-medium text-text-primary">
            No projects yet
          </p>
          <p className="mt-1 text-sm text-text-secondary">
            Create your first tender project to get started.
          </p>
          <button
            className="mt-4 rounded-md bg-accent px-5 py-2 text-sm font-semibold text-white hover:bg-accent-hover"
            onClick={openDialog}
          >
            Create tender project
          </button>
        </motion.div>
      )}

      {/* Projects grid */}
      {!loading && !error && activeProjects.length > 0 && (
        <div className="space-y-6">
          {/* Active projects */}
          <div>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
              Active projects
            </h3>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {activeProjects.map((project) => (
                <ProjectCard key={project.id} project={project} />
              ))}
            </div>
          </div>

          {/* Archived projects */}
          {archivedProjects.length > 0 && (
            <div>
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                Archived
              </h3>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {archivedProjects.map((project) => (
                  <ProjectCard key={project.id} project={project} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Create project dialog */}
      <AnimatePresence>
        {showDialog && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center bg-[#172033]/30"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeDialog}
          >
            <motion.div
              className="w-full max-w-md rounded-lg border border-border bg-surface p-6 shadow-lg"
              role="dialog"
              aria-modal="true"
              aria-labelledby="create-project-title"
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              onClick={(e) => e.stopPropagation()}
              ref={dialogRef}
            >
              <h3
                id="create-project-title"
                className="text-lg font-semibold text-text-primary"
              >
                New tender project
              </h3>
              <input
                type="text"
                placeholder="Project name"
                aria-label="Project name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={creating}
                autoFocus
                className={cn(
                  "mt-4 w-full rounded-lg border border-border bg-background px-4 py-2.5",
                  "text-sm text-text-primary placeholder:text-text-tertiary",
                  "focus:ring-2 focus:ring-accent focus:outline-none",
                )}
              />
              <div className="mt-6 flex justify-end gap-3">
                <button
                  className="rounded-lg px-4 py-2 text-sm text-text-secondary hover:text-text-primary"
                  onClick={closeDialog}
                  disabled={creating}
                >
                  Cancel
                </button>
                <button
                  className={cn(
                    "rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white",
                    "hover:bg-accent-hover disabled:opacity-60",
                  )}
                  onClick={() => void handleCreate()}
                  disabled={creating || !newName.trim()}
                >
                  {creating ? "Creating…" : "Create"}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function ProjectCard({ project }: { project: Project }) {
  const config = statusConfig[project.status];
  const isArchived = project.status === "archived";

  return (
    <Link href={`/projects/${project.id}`}>
      <motion.div
        className={cn(
          "group relative flex flex-col rounded-lg border p-5",
          "bg-surface transition-colors duration-150",
          isArchived
            ? "border-border/30 opacity-60"
            : "border-border hover:border-border-hover hover:bg-surface-elevated",
        )}
        whileHover={{ y: -1 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
      >
        <div className="mb-4 flex items-start justify-between">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10">
            <FileText className="h-5 w-5 text-accent" />
          </div>
          <span
            className={cn(
              "status-pill px-2.5 py-0.5 text-xs font-medium",
              config.className,
            )}
          >
            {config.label}
          </span>
        </div>

        <h3 className="font-semibold text-text-primary">{project.name}</h3>
        {project.external_tender_id && (
          <p className="mt-1 text-sm text-text-secondary">
            {project.external_tender_id}
          </p>
        )}

        <div className="mt-4 flex items-center justify-between text-xs text-text-tertiary">
          <span>Updated {formatDate(project.updated_at)}</span>
          <MoreHorizontal className="h-4 w-4 opacity-0 transition-opacity group-hover:opacity-100" />
        </div>
      </motion.div>
    </Link>
  );
}
