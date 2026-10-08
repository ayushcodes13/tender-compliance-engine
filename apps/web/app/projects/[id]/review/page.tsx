"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { ArrowLeft, AlertCircle } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { TenderReviewWorkspace } from "@/components/tender-review-workspace";
import { api, DocumentItem, Project } from "@/lib/api/client";

const isUuid = (value: string | null): value is string =>
  value !== null &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value
  );

export default function ProjectReviewPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const searchParams = useSearchParams();
  const rawDocumentId = searchParams.get("documentId");
  const rawVersion = searchParams.get("version");
  const hasSourceVersionRequest = rawDocumentId !== null || rawVersion !== null;
  const requestedDocumentId = isUuid(rawDocumentId) ? rawDocumentId : undefined;
  const parsedVersion = Number(rawVersion);
  const requestedVersion =
    Number.isInteger(parsedVersion) && parsedVersion > 0
      ? parsedVersion
      : undefined;
  const rawRequirementId = searchParams.get("requirementId");
  const initialRequirementId = isUuid(rawRequirementId)
    ? rawRequirementId
    : undefined;
  const pageParam = Number(searchParams.get("page"));
  const initialSourcePage =
    requestedDocumentId &&
    requestedVersion &&
    Number.isInteger(pageParam) &&
    pageParam > 0
      ? pageParam
      : undefined;
  const rawSourceQuote = searchParams.get("sourceQuote");
  const initialSourceQuote =
    rawSourceQuote && rawSourceQuote.length <= 2048 ? rawSourceQuote : undefined;

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
        const proj = await api.fetchProject(projectId);
        setProject(proj);

        const docs = await api.fetchDocuments(projectId);
        let target: DocumentItem | undefined;
        if (hasSourceVersionRequest) {
          target = requestedDocumentId && requestedVersion
            ? docs.find(
                (item) =>
                  item.document_id === requestedDocumentId &&
                  item.version_number === requestedVersion
              )
            : undefined;
        } else {
          // Standard review navigation picks the latest parsed version;
          // source links bind to the exact document/version from the matrix.
          const parsed = docs
            .filter((d) => d.processing_status === "parsed")
            .sort(
              (a, b) =>
                new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
            );
          target = parsed.length > 0 ? parsed[0] : docs[docs.length - 1];
        }
        if (!target) {
          setError(
            hasSourceVersionRequest
              ? "The cited tender document version is unavailable. Review the current project sources before relying on this matrix link."
              : "No documents uploaded yet. Upload a document from the project page."
          );
          return;
        }
        setDocument(target);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load project");
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId, hasSourceVersionRequest, requestedDocumentId, requestedVersion]);

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
          <div
            className="empty-list"
            style={{ marginTop: "24px" }}
          >
            <AlertCircle size={18} aria-hidden="true" />
            <strong>
              {error ?? "No document available for review"}
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
      <TenderReviewWorkspace
        projectId={projectId}
        documentId={document.document_id}
        version={document.version_number}
        document={document}
        initialRequirementId={initialRequirementId}
        initialSourcePage={initialSourcePage}
        initialSourceQuote={initialSourceQuote}
      />
    </AppShell>
  );
}
