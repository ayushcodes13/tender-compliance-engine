/**
 * Frontend API client for the Tender Compliance Engine backend.
 *
 * This module is the single boundary between the React/Next.js frontend and
 * the FastAPI backend. All API calls go through {@link apiFetch}, which
 * attaches the development identity headers and serializes JSON bodies.
 *
 * Dev identity: In development, the backend resolves identity from the
 * `X-Dev-User-Id` / `X-Dev-Organization-Id` headers. The backend auto-creates
 * the User and Organization rows but **requires** a Membership row to already
 * exist. Use `.env.local` with matching UUIDs and seed a Membership in your
 * local database before the frontend can talk to the API.
 */

export type ProjectStatus =
  | "draft"
  | "tender_uploaded"
  | "documents_processing"
  | "requirements_extracted"
  | "review_in_progress"
  | "matrix_ready"
  | "exported"
  | "archived";

export type Project = {
  id: string;
  organization_id: string;
  name: string;
  external_tender_id: string | null;
  status: ProjectStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectCreate = {
  name: string;
  external_tender_id?: string | null;
};

export type ProjectRename = {
  name: string;
};

/** Processing status of a single uploaded document version. */
export type DocumentProcessingStatus =
  | "uploaded"
  | "processing"
  | "parsed"
  | "ocr_warning"
  | "failed";

/** A single persisted document version returned by `GET /projects/{id}/documents`. */
export type DocumentItem = {
  document_id: string;
  display_name: string;
  document_type: string;
  version_number: number;
  sha256: string;
  mime_type: string;
  size_bytes: number;
  processing_status: DocumentProcessingStatus;
  created_at: string;
};

/** Response from `POST /projects/{id}/upload`. */
export type UploadResponse = DocumentItem & {
  stored_object_id: string;
  storage_key: string;
  filename: string;
  content_type: string;
  content_length: number;
  checksum_sha256: string;
  project_status: ProjectStatus;
  uploaded_at: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Headers for the development identity mode. */
function devHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const userId = process.env.NEXT_PUBLIC_DEV_USER_ID;
  const orgId = process.env.NEXT_PUBLIC_DEV_ORG_ID;
  if (userId) headers["x-dev-user-id"] = userId;
  if (orgId) headers["x-dev-organization-id"] = orgId;
  return headers;
}

/** Low-level wrapper around fetch that attaches the API base URL and dev headers. */
async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...devHeaders(),
      ...init.headers,
    },
  });
}

/** Parse a Response, throwing a descriptive Error on non-2xx. */
async function expectJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail;
    } catch {
      // response body is not JSON — fall back to status text
    }
    throw new Error(detail ?? `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

/**
 * Fetch variant that omits the default `Content-Type: application/json` header.
 *
 * This is required for `FormData` uploads: the browser must set the boundary
 * itself, and a static `Content-Type` header would override it.
 */
async function apiFetchFile(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...devHeaders(),
      ...init.headers,
    },
  });
}

/**
 * Public API surface consumed by React components.
 *
 * Each method maps directly to a project-lifecycle route on the backend.
 */
export const api = {
  fetchProjects: () => apiFetch("/projects").then((r) => expectJson<Project[]>(r)),

  fetchProject: (id: string) =>
    apiFetch(`/projects/${id}`).then((r) => expectJson<Project>(r)),

  createProject: (input: ProjectCreate) =>
    apiFetch("/projects", {
      method: "POST",
      body: JSON.stringify(input),
    }).then((r) => expectJson<Project>(r)),

  renameProject: (id: string, input: ProjectRename) =>
    apiFetch(`/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }).then((r) => expectJson<Project>(r)),

  archiveProject: (id: string) =>
    apiFetch(`/projects/${id}/archive`, { method: "POST" }).then((r) =>
      expectJson<Project>(r)
    ),

  reopenProject: (id: string) =>
    apiFetch(`/projects/${id}/reopen`, { method: "POST" }).then((r) =>
      expectJson<Project>(r)
    ),

  fetchDocuments: (projectId: string) =>
    apiFetch(`/projects/${projectId}/documents`).then((r) =>
      expectJson<DocumentItem[]>(r)
    ),

  uploadDocument: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiFetchFile(`/projects/${projectId}/upload`, {
      method: "POST",
      body: form,
    }).then((r) => expectJson<UploadResponse>(r));
  },
};
