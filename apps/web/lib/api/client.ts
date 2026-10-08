/**
 * Frontend API client for the Tender Compliance Engine backend.
 *
 * This module is the single boundary between the React/Next.js frontend and
 * the FastAPI backend. Browser traffic defaults to the same-origin
 * `/api/backend/*` proxy so deployments do not need to expose the API or
 * configure browser CORS just to run the product.
 *
 * Development identity headers remain supported when explicitly configured.
 * The bundled Docker pilot uses backend `single_workspace` mode instead, so
 * no browser identity headers or manual membership seed are required.
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
  | "queued"
  | "processing"
  | "parsed"
  | "partial"
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
  parser_name: string | null;
  parser_version: string | null;
  ocr_name: string | null;
  ocr_version: string | null;
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

export type RetryProcessingResponse = {
  run_id: string;
  status: DocumentProcessingStatus;
};

export type ProcessingRun = {
  id: string;
  run_id: string;
  attempt: number;
  stage: "parse" | "ocr" | "cleanup" | "extract";
  status: "started" | "running" | "completed" | "failed" | "retry";
  error_type: string | null;
  started_at: string;
  completed_at: string | null;
};

/** Requirement review state (Phase 1). */
export type RequirementReviewState =
  | "unreviewed"
  | "reviewed"
  | "needs_clarification"
  | "ocr_warning";

/** A single requirement in list view. */
export type RequirementSummary = {
  id: string;
  requirement_type: string;
  normalized_text: string;
  uncertainty: string;
  review_state: RequirementReviewState;
  ocr_warning: boolean;
  clause_number: string | null;
  display_order: number | null;
  mandatory: boolean | null;
  superseded: boolean;
  created_at: string;
};

/** A single structured constraint. */
export type ConstraintSummary = {
  id: string;
  parameter: string;
  operator: string | null;
  numeric_value: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
  unit: string | null;
  tolerance: number | null;
  qualitative_condition: string | null;
  normalization_state: string;
  raw_fragment: string;
  created_at: string;
};

/** A source anchor for a requirement. */
export type RequirementSourceSummary = {
  id: string;
  requirement_id: string;
  page_number: number;
  clause_number: string | null;
  location_type: string;
  source_text: string | null;
  quote_text: string | null;
  ocr_confidence: number | null;
};

/** Full detail view of a requirement. */
export type RequirementDetail = {
  id: string;
  document_version_id: string;
  requirement_type: string;
  normalized_text: string;
  raw_source: string;
  uncertainty: string;
  review_state: RequirementReviewState;
  ocr_warning: boolean;
  clause_number: string | null;
  reconciliation_group_id: string | null;
  display_order: number | null;
  mandatory: boolean | null;
  superseded: boolean;
  created_at: string;
  updated_at: string | null;
  constraints: ConstraintSummary[];
  sources: RequirementSourceSummary[];
  revisions: RevisionSummary[];
  notes: NoteSummary[];
  categories: CategorySummary[];
};

/** A single immutable revision row (CP38). */
export type RevisionSummary = {
  id: string;
  previous_normalized_text: string;
  updated_at_at_edit: string | null;
  actor_id: string | null;
  note: string | null;
  created_at: string;
};

/** Request to edit a requirement's normalized text (CP38). */
export type EditRequirementRequest = {
  normalized_text: string;
  expected_updated_at?: string | null;
  note?: string | null;
};

/** Error response for concurrent edits (CP38). */
export type ConcurrentEditError = {
  error: string;
  message: string;
  current_updated_at: string | null;
};

/** A single reviewer note on a requirement (CP39). */
export type NoteSummary = {
  id: string;
  requirement_id: string;
  actor_id: string | null;
  text: string;
  created_at: string;
  updated_at: string | null;
};

/** Request to add a reviewer note (CP39). */
export type NoteCreateRequest = {
  text: string;
};

/** A project-scoped hierarchical category (CP39). */
export type CategorySummary = {
  id: string;
  project_id: string;
  parent_id: string | null;
  name: string;
  display_order: number;
};

/** Request to assign a category (CP39). */
export type CategoryAssignmentRequest = {
  category_id: string;
};

/** Request to split a requirement (CP39). */
export type SplitRequirementRequest = {
  new_requirements: SplitChildSpec[];
};

export type SplitChildSpec = {
  normalized_text: string;
  raw_source: string;
  requirement_type?: string;
  clause_number?: string;
  uncertainty?: string;
  ocr_warning?: boolean;
};

/** Request to merge requirements (CP39). */
export type MergeRequirementRequest = {
  requirement_ids: string[];
  merged_normalized_text: string;
  merged_raw_sources: string[];
};

/** Request to supersede a requirement (CP39). */
export type SupersedeRequirementRequest = {
  superseded_by?: string | null;
  note?: string | null;
};

/** Request to set mandatory tri-state flag (CP39). */
export type SetMandatoryRequest = {
  value: boolean | null;
};

/** Request to persist a new display order (CP39). */
export type ReorderRequirementsRequest = {
  order: string[];
};

/** Real review counts for a document version (CP40). */
export type ReviewCountsResponse = {
  total: number;
  active: number;
  unreviewed: number;
  reviewed: number;
  needs_clarification: number;
  ocr_warning: number;
  superseded: number;
};

/** Request to create a category (CP39). */
export type CategoryCreateRequest = {
  name: string;
  parent_id?: string | null;
};

/** Paginated list of requirements. */
export type RequirementListResponse = {
  items: RequirementSummary[];
  total: number;
  limit: number;
  offset: number;
};

/** Page metadata for the source viewer. */
export type PageResponse = {
  page_number: number;
  has_image: boolean;
  ocr_needed: boolean;
  ocr_confidence: number | null;
  cleaned_text: string | null;
  extracted_text: string | null;
  structural_metadata: Record<string, unknown> | null;
  created_at: string;
};

/** A source anchor (bounding box) for overlay on the source viewer. */
export type SourceAnchor = {
  anchor_id?: string;
  requirement_id: string | null;
  clause_number: string | null;
  page_number: number;
  location_type: string;
  source_text: string | null;
  quote_text: string | null;
  bbox: { x: number; y: number; width: number; height: number } | null;
  ocr_confidence: number | null;
};

/** A single matrix row from the canonical Phase 1 projection (CP41). */
export type MatrixRowResponse = {
  serial: number;
  requirement_id: string;
  tender_requirement: string;
  category: string | null;
  clause: string | null;
  source_page: number | null;
  mandatory: boolean | null;
  user_notes: string | null;
  review_status: RequirementReviewState;
};

/** Metadata for a matrix XLSX export artifact (CP42). */
export type ExportArtifactResponse = {
  id: string;
  document_version_id: string;
  stored_object_id: string | null;
  actor_id: string | null;
  status: "completed" | "failed";
  error_message: string | null;
  requirement_count: number;
  workbook_sha256: string;
  generated_at: string | null;
  export_format?: "xlsx" | "docx" | "pdf" | null;
  validation_status: "not_run" | "passed" | "needs_review" | "failed";
  validation_report: {
    artifact_integrity?: "passed" | "failed";
    expected_rows?: number;
    actual_rows?: number;
    checked_columns?: number;
    checked_cells?: number;
    issues?: { row_id: string; code: string; field?: string }[];
    source_validation?: {
      status: "passed" | "needs_review";
      checked_rows: number;
      llm_assisted_rows?: string[];
      issues: { row_id: string; code: string }[];
      llm_fallback_results?: {
        row_id: string;
        page_number: number;
        status: string;
        provider?: string;
        model?: string;
        call_status?: string;
      }[];
    };
    window_processing?: {
      status: "complete" | "incomplete" | "not_available";
      completeness_proven: false;
      obligation_audit_status?:
        | "no_potential_omissions"
        | "potential_omissions"
        | "audit_failed"
        | "incomplete"
        | "not_available";
      obligation_audited_windows?: number;
      obligation_audit_failed_windows?: {
        window_index: number;
        chunk_id: string;
        pages: number[];
      }[];
      potential_omissions?: {
        window_index: number;
        pages: number[];
        source_quote: string;
      }[];
      expected_windows?: number;
      audited_windows?: number;
      missing_window_count?: number;
      failed_windows?: { window_index: number; chunk_id: string; pages: number[] }[];
      zero_candidate_windows?: { window_index: number; chunk_id: string; pages: number[] }[];
      ocr_warning_windows?: { window_index: number; chunk_id: string; pages: number[] }[];
      message: string;
    };
  } | null;
};

export type FinalMatrixRowResponse = {
  serial: number;
  requirement_id: string;
  tender_requirement: string;
  category: string | null;
  clause: string | null;
  source_page: number | null;
  mandatory: boolean | null;
  user_notes: string | null;
  review_status: string;
  normalized_text: string;
  raw_source: string;
  uncertainty: string;
  ocr_warning: boolean;
  evidence_id: string | null;
  evidence_score: number | null;
  evidence_oem_document: string | null;
  evidence_oem_version: number | null;
  vendor_spec_parameter: string | null;
  vendor_spec_value: number | null;
  vendor_spec_unit: string | null;
  vendor_spec_lower_bound: number | null;
  vendor_spec_upper_bound: number | null;
  vendor_spec_source_text: string | null;
  vendor_spec_source_page: number | null;
  vendor_spec_extraction_method: string | null;
  vendor_spec_issues: string[] | null;
  assessment_status: ComplianceStatus | null;
  assessment_suggested_status: ComplianceStatus | null;
  assessment_reason_code: string | null;
  assessment_reason_text: string | null;
  assessment_is_confirmed: boolean | null;
  assessment_reviewer_id: string | null;
  assessment_reviewed_at: string | null;
  assessment_version: number | null;
  has_unresolved_conflict: boolean;
  clarification_statuses: string[];
  deviation_statuses: string[];
};

export type SubmissionResponse = {
  id: string;
  project_id: string;
  document_version_id: string;
  version_number: number;
  status: "draft" | "locked" | "approved" | "revoked";
  approver_id: string | null;
  approved_at: string | null;
  assessment_snapshot: Array<Record<string, unknown>>;
  matrix_sha256: string;
  matrix_export_id: string | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
};

/** Evidence review state (Phase 2 — curation, not compliance). */
export type EvidenceReviewState = "proposed" | "accepted" | "rejected";

/** A source location anchor for persisted evidence. */
export type EvidenceLocationResponse = {
  page_number: number;
  clause_number: string | null;
  char_start: number | null;
  char_end: number | null;
  location_type: string;
  source_text: string | null;
  ocr_confidence: number | null;
};

/** A persisted evidence candidate with its locations. */
export type EvidenceResponse = {
  id: string;
  oem_document_version_id: string;
  score: number | null;
  retrieval_method: string;
  review_state: EvidenceReviewState;
  created_at: string;
  locations: EvidenceLocationResponse[];
};

/** A proposed evidence candidate returned by retrieval. */
export type EvidenceCandidateResponse = {
  oem_document_version_id: string;
  oem_document_display_name: string | null;
  oem_document_type: string | null;
  version_number: number;
  score: number;
  matched_terms: string[];
  page_number: number;
  char_start: number | null;
  char_end: number | null;
  source_text: string | null;
};

/** Request body for proposing evidence. */
export type EvidenceProposeRequest = {
  query_terms: string[];
  k?: number;
  persist?: boolean;
};

/** Latest OEM/vendor document version attached to a project. */
export type OemDocumentItem = {
  document_id: string;
  display_name: string;
  document_type: string;
  vendor_name: string | null;
  product_name: string | null;
  product_sku: string | null;
  version_number: number;
  sha256: string;
  mime_type: string;
  size_bytes: number;
  processing_status: DocumentProcessingStatus;
  parser_name: string | null;
  parser_version: string | null;
  ocr_name: string | null;
  ocr_version: string | null;
  created_at: string;
};

export type OemUploadResponse = {
  stored_object_id: string;
  document_id: string;
  version_number: number;
  storage_key: string;
  filename: string;
  content_type: string;
  content_length: number;
  checksum_sha256: string;
  processing_status: DocumentProcessingStatus;
  uploaded_at: string;
};

export type ComplianceStatus =
  | "compliant"
  | "non_compliant"
  | "partial"
  | "not_demonstrated"
  | "conflict"
  | "human_review_required";

export type ComparisonResultResponse = {
  verdict?: string | null;
  tender_text?: string | null;
  vendor_text?: string | null;
  comparison_rule?: string | null;
  conversion?: string | null;
  reasons?: string[] | null;
  tender_value?: number | null;
  vendor_value?: number | null;
  tender_unit?: string | null;
  vendor_unit?: string | null;
  normalized_tender_value?: number | null;
  normalized_vendor_value?: number | null;
  details?: Record<string, unknown> | null;
};

export type ComplianceAssessmentResponse = {
  id: string;
  project_id: string;
  requirement_id: string;
  evidence_id: string | null;
  vendor_spec_id: string | null;
  suggested_status: ComplianceStatus;
  status: ComplianceStatus;
  reason_code: string;
  reason_text: string | null;
  comparison_result: ComparisonResultResponse | null;
  assessment_version: number;
  is_confirmed_by_human: boolean;
  reviewer_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AssessmentCommentResponse = {
  id: string;
  assessment_id: string;
  project_id: string;
  author_id: string | null;
  comment_type: string;
  comment: string;
  assessment_version: number;
  created_at: string;
};

export type ReviewConflict = {
  id: string;
  conflict_type: string;
  parameter: string | null;
  entity: string | null;
  resolution: "unresolved" | "accepted" | "rejected";
  sources: Array<Record<string, unknown>>;
  tender_claim: string | null;
};

export type ReviewClarification = {
  id: string;
  question: string;
  context: Record<string, unknown>;
  status: string;
  asked_at: string;
  answer: string | null;
  answered_at: string | null;
};

export type ReviewDeviation = {
  id: string;
  deviation_type: string;
  original_requirement: string;
  proposed_alternative: string | null;
  status: string;
  proposed_at: string;
  reviewed_at: string | null;
};

export type RequirementComplianceReview = {
  requirement_id: string;
  assessment: {
    id: string;
    suggested_status: ComplianceStatus;
    status: ComplianceStatus;
    reason_code: string;
    reason_text: string | null;
    is_confirmed_by_human: boolean;
    reviewer_id: string | null;
    reviewed_at: string | null;
    assessment_version: number;
    evidence_id: string | null;
    vendor_spec_id: string | null;
    comparison_result: ComparisonResultResponse | null;
  };
  conflicts: ReviewConflict[];
  clarifications: ReviewClarification[];
  deviations: ReviewDeviation[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api/backend";

/** Headers for the development identity mode. */
function devHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const userId = process.env.NEXT_PUBLIC_DEV_USER_ID;
  const orgId = process.env.NEXT_PUBLIC_DEV_ORG_ID;
  if (userId) headers["x-dev-user-id"] = userId;
  if (orgId) headers["x-dev-organization-id"] = orgId;
  return headers;
}

const GENERIC_SERVICE_ERROR =
  "We couldn't complete that request. Please try again. If it keeps failing, use the reference ID shown here when reporting it.";

async function fetchApi(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new Error(
      "Cannot reach the Tender Compliance service. Check that the product stack is running, then retry."
    );
  }
}

/** Low-level wrapper around fetch that attaches the API base URL and dev headers. */
async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetchApi(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...devHeaders(),
      ...init.headers,
    },
  });
}

/** Parse a Response, exposing useful validation errors but masking internals. */
async function expectJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const correlationId = response.headers.get("x-correlation-id");
    let detail: string | undefined;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = typeof body.detail === "string" ? body.detail : undefined;
    } catch {
      // Non-JSON errors intentionally fall through to status-based copy.
    }

    if (response.status === 400 || response.status === 409 || response.status === 422) {
      throw new Error(detail ?? "The request could not be accepted. Check the input and try again.");
    }
    if (response.status === 401) {
      // No login flow exists to retry: this pilot resolves identity from
      // deployment configuration, so telling someone to sign in again would
      // send them looking for a form that was deliberately removed.
      throw new Error(
        "This deployment did not recognize your access. Check that you are reaching it the way the pilot provides, or contact whoever runs it.",
      );
    }
    if (response.status === 403) {
      throw new Error("You do not have access to this project or action.");
    }
    if (response.status === 404) {
      throw new Error(detail ?? "The requested project or source could not be found.");
    }
    if (response.status === 413) {
      throw new Error("That file is larger than the configured upload limit.");
    }

    const suffix = correlationId ? ` Reference: ${correlationId}.` : "";
    throw new Error(`${GENERIC_SERVICE_ERROR}${suffix}`);
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
  return fetchApi(path, {
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

  retryDocumentProcessing: (
    projectId: string,
    documentId: string,
    version: number
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/retry`,
      { method: "POST" }
    ).then((r) => expectJson<RetryProcessingResponse>(r)),

  fetchProcessingRuns: (
    projectId: string,
    documentId: string,
    version: number
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/runs`
    ).then((r) => expectJson<ProcessingRun[]>(r)),

  // --- Requirements (CP35) ---

  fetchRequirements: (
    projectId: string,
    documentId: string,
    version: number,
    params?: { review_state?: string; requirement_type?: string; search?: string; limit?: number; offset?: number }
  ) => {
    const q = new URLSearchParams();
    if (params?.review_state) q.set("review_state", params.review_state);
    if (params?.requirement_type) q.set("requirement_type", params.requirement_type);
    if (params?.search) q.set("search", params.search);
    if (params?.limit !== undefined) q.set("limit", String(params.limit));
    if (params?.offset !== undefined) q.set("offset", String(params.offset));
    const qs = q.toString();
    return apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements${qs ? `?${qs}` : ""}`
    ).then((r) => expectJson<RequirementListResponse>(r));
  },

  fetchRequirement: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}`
    ).then((r) => expectJson<RequirementDetail>(r)),

  // --- Requirement structure (CP39) ---

  splitRequirement: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string,
    body: SplitRequirementRequest
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}/split`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    ).then((r) => expectJson<RequirementSummary[]>(r)),

  mergeRequirements: (
    projectId: string,
    documentId: string,
    version: number,
    body: MergeRequirementRequest
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/merge`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    ).then((r) => expectJson<RequirementSummary>(r)),

  supersedeRequirement: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string,
    body?: SupersedeRequirementRequest
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}/supersede`,
      {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      }
    ).then((r) => expectJson<RequirementSummary>(r)),

  setMandatory: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string,
    body: SetMandatoryRequest
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}/mandatory`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      }
    ).then((r) => expectJson<RequirementSummary>(r)),

  assignCategory: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string,
    body: CategoryAssignmentRequest
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}/categories`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    ).then((r) => expectJson<RequirementDetail>(r)),

  unassignCategory: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string,
    categoryId: string
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}/categories/${categoryId}`,
      {
        method: "DELETE",
      }
    ).then((r) => expectJson<RequirementDetail>(r)),

  reorderRequirements: (
    projectId: string,
    documentId: string,
    version: number,
    body: ReorderRequirementsRequest
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/reorder`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      }
    ).then((r) => expectJson<RequirementSummary[]>(r)),

  addNote: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string,
    body: NoteCreateRequest
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}/notes`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    ).then((r) => expectJson<NoteSummary>(r)),

  listNotes: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}/notes`
    ).then((r) => expectJson<NoteSummary[]>(r)),

  // --- Categories (CP39) ---

  listCategories: (projectId: string) =>
    apiFetch(`/projects/${projectId}/categories`).then((r) =>
      expectJson<CategorySummary[]>(r)
    ),

  // --- Source viewer (CP36) ---

  fetchPage: (
    projectId: string,
    documentId: string,
    version: number,
    pageNumber: number
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/pages/${pageNumber}`
    ).then((r) => expectJson<PageResponse>(r)),

  fetchPageImage: (
    projectId: string,
    documentId: string,
    version: number,
    pageNumber: number
  ): Promise<Blob> =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/pages/${pageNumber}/image`
    ).then((r) => {
      if (!r.ok) {
        throw new Error(`HTTP ${r.status}: ${r.statusText}`);
      }
      return r.blob();
    }),

  fetchPageSources: (
    projectId: string,
    documentId: string,
    version: number,
    pageNumber: number,
    quote?: string
  ) => {
    const query = quote ? `?quote=${encodeURIComponent(quote)}` : "";
    return apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/pages/${pageNumber}/sources${query}`
    ).then((r) => expectJson<SourceAnchor[]>(r));
  },

  // --- Requirement edit (CP38) ---

  editRequirement: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string,
    body: EditRequirementRequest
  ): Promise<RequirementDetail> =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      }
    ).then((r) => expectJson<RequirementDetail>(r)),

  editRequirementOrError: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string,
    body: EditRequirementRequest
  ): Promise<{ data?: RequirementDetail; error?: ConcurrentEditError }> =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      }
    ).then((r) => {
      if (r.ok) return r.json().then((data) => ({ data: data as RequirementDetail }));
      return r.json().then((err) => ({
        error: err as ConcurrentEditError,
      }));
    }),

  fetchRevisionHistory: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}/revisions`
    ).then((r) => expectJson<RevisionSummary[]>(r)),

  // --- Review state machine (CP40) ---

  markReviewed: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string,
    override_uncertainty = false
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}/mark-reviewed`,
      {
        method: "POST",
        body: JSON.stringify({ override_uncertainty }),
      }
    ).then((r) => expectJson<RequirementDetail>(r)),

  reopenRequirement: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}/reopen`,
      { method: "POST" }
    ).then((r) => expectJson<RequirementDetail>(r)),

  escalateRequirement: (
    projectId: string,
    documentId: string,
    version: number,
    requirementId: string
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/requirements/${requirementId}/escalate`,
      { method: "POST" }
    ).then((r) => expectJson<RequirementDetail>(r)),

  fetchReviewCounts: (
    projectId: string,
    documentId: string,
    version: number
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/review-counts`
    ).then((r) => expectJson<ReviewCountsResponse>(r)),

  // --- Matrix projection (CP41) ---

  fetchMatrix: (
    projectId: string,
    documentId: string,
    version: number
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/matrix`
    ).then((r) => expectJson<MatrixRowResponse[]>(r)),

  // --- XLSX export (CP42) ---

  createMatrixExport: (
    projectId: string,
    documentId: string,
    version: number
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/exports`,
      { method: "POST" }
    ).then((r) => expectJson<ExportArtifactResponse>(r)),

  fetchExports: (
    projectId: string,
    documentId: string,
    version: number
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/exports`
    ).then((r) => expectJson<ExportArtifactResponse[]>(r)),

  downloadMatrixExport: async (
    projectId: string,
    documentId: string,
    version: number,
    exportId: string
  ): Promise<Blob> => {
    const resp = await fetch(
      `${API_URL}/projects/${projectId}/documents/${documentId}/versions/${version}/exports/${exportId}`,
      {
        headers: devHeaders(),
      }
    );
    if (!resp.ok) {
      throw new Error(`Download failed: ${resp.status}`);
    }
    return resp.blob();
  },

  // --- Evidence (CP50/CP51) ---

  fetchEvidence: (
    projectId: string,
    requirementId: string,
    params?: { review_state?: string }
  ) => {
    const q = new URLSearchParams();
    if (params?.review_state) q.set("review_state", params.review_state);
    return apiFetch(
      `/projects/${projectId}/requirements/${requirementId}/evidence${q.toString() ? `?${q.toString()}` : ""}`
    ).then((r) => expectJson<EvidenceResponse[]>(r));
  },

  proposeEvidence: (
    projectId: string,
    requirementId: string,
    body: EvidenceProposeRequest
  ) =>
    apiFetch(
      `/projects/${projectId}/requirements/${requirementId}/evidence/propose`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    ).then((r) => expectJson<EvidenceCandidateResponse[]>(r)),

  curateEvidence: (
    projectId: string,
    requirementId: string,
    evidenceId: string,
    reviewState: string
  ) =>
    apiFetch(
      `/projects/${projectId}/requirements/${requirementId}/evidence/${evidenceId}/curate?review_state=${reviewState}`,
      { method: "POST" }
    ).then((r) => expectJson<EvidenceResponse>(r)),

  // --- OEM/vendor documents (CP49) ---

  fetchOemDocuments: (projectId: string) =>
    apiFetch(`/projects/${projectId}/oem-documents`).then((r) =>
      expectJson<OemDocumentItem[]>(r)
    ),

  uploadOemDocument: (
    projectId: string,
    file: File,
    metadata?: {
      document_type?: string;
      vendor_name?: string;
      product_name?: string;
      product_sku?: string;
    }
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("document_type", metadata?.document_type ?? "datasheet");
    if (metadata?.vendor_name) form.append("vendor_name", metadata.vendor_name);
    if (metadata?.product_name) form.append("product_name", metadata.product_name);
    if (metadata?.product_sku) form.append("product_sku", metadata.product_sku);
    return apiFetchFile(`/projects/${projectId}/oem-documents/upload`, {
      method: "POST",
      body: form,
    }).then((r) => expectJson<OemUploadResponse>(r));
  },

  // --- Human compliance review (CP54/CP56–CP58) ---

  assessRequirement: (projectId: string, requirementId: string) =>
    apiFetch(`/projects/${projectId}/requirements/${requirementId}/assess`, {
      method: "POST",
    }).then((r) => expectJson<ComplianceAssessmentResponse>(r)),

  fetchComplianceAssessment: (projectId: string, requirementId: string) =>
    apiFetch(
      `/projects/${projectId}/requirements/${requirementId}/compliance-assessment`
    ).then((r) => expectJson<ComplianceAssessmentResponse | null>(r)),

  fetchRequirementComplianceReview: (
    projectId: string,
    requirementId: string
  ) =>
    apiFetch(
      `/projects/${projectId}/requirements/${requirementId}/review`
    ).then((r) => expectJson<RequirementComplianceReview>(r)),

  confirmAssessment: (projectId: string, assessmentId: string) =>
    apiFetch(
      `/projects/${projectId}/compliance-assessments/${assessmentId}/confirm`,
      { method: "POST" }
    ).then((r) => expectJson<ComplianceAssessmentResponse>(r)),

  overrideAssessment: (
    projectId: string,
    assessmentId: string,
    body: { status: ComplianceStatus; reason: string; evidence_id?: string | null }
  ) =>
    apiFetch(
      `/projects/${projectId}/compliance-assessments/${assessmentId}/override`,
      { method: "POST", body: JSON.stringify(body) }
    ).then((r) => expectJson<ComplianceAssessmentResponse>(r)),

  reopenAssessment: (
    projectId: string,
    assessmentId: string,
    reason?: string
  ) =>
    apiFetch(
      `/projects/${projectId}/compliance-assessments/${assessmentId}/reopen`,
      {
        method: "POST",
        body: reason ? JSON.stringify({ comment: reason }) : undefined,
      }
    ).then((r) => expectJson<ComplianceAssessmentResponse>(r)),

  fetchAssessmentComments: (projectId: string, assessmentId: string) =>
    apiFetch(
      `/projects/${projectId}/compliance-assessments/${assessmentId}/comments`
    ).then((r) => expectJson<AssessmentCommentResponse[]>(r)),

  addAssessmentComment: (
    projectId: string,
    assessmentId: string,
    comment: string
  ) =>
    apiFetch(
      `/projects/${projectId}/compliance-assessments/${assessmentId}/comments`,
      { method: "POST", body: JSON.stringify({ comment }) }
    ).then((r) => expectJson<AssessmentCommentResponse>(r)),

  resolveConflict: (
    projectId: string,
    conflictId: string,
    resolution: "accepted" | "rejected",
    notes?: string
  ) =>
    apiFetch(`/api/projects/${projectId}/conflicts/${conflictId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ resolution, notes: notes ?? null }),
    }).then((r) => expectJson<Record<string, unknown>>(r)),

  autoGenerateClarifications: (projectId: string, requirementId: string) =>
    apiFetch(
      `/api/projects/${projectId}/requirements/${requirementId}/clarifications/auto`,
      { method: "POST" }
    ).then((r) => expectJson<ReviewClarification[]>(r)),

  reviewDeviation: (
    projectId: string,
    deviationId: string,
    status: "accepted" | "rejected",
    reviewNotes?: string
  ) =>
    apiFetch(`/api/projects/${projectId}/deviations/${deviationId}/review`, {
      method: "POST",
      body: JSON.stringify({
        status,
        review_notes: reviewNotes ?? null,
      }),
    }).then((r) => expectJson<Record<string, unknown>>(r)),

  // --- Final compliance matrix / exports / submissions (CP59–CP61) ---

  fetchFinalMatrix: (
    projectId: string,
    documentId: string,
    version: number
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/final-matrix`
    ).then((r) => expectJson<FinalMatrixRowResponse[]>(r)),

  createFinalMatrixExport: (
    projectId: string,
    documentId: string,
    version: number,
    format: "xlsx" | "docx" | "pdf"
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/final-matrix/exports?fmt=${format}`,
      { method: "POST" }
    ).then((r) => expectJson<ExportArtifactResponse>(r)),

  createVendorResponseSheetExport: (
    projectId: string,
    documentId: string,
    version: number
  ) =>
    apiFetch(
      `/projects/${projectId}/documents/${documentId}/versions/${version}/final-matrix/exports?fmt=docx&template=vendor-response`,
      { method: "POST" }
    ).then((r) => expectJson<ExportArtifactResponse>(r)),

  downloadExport: async (
    projectId: string,
    documentId: string,
    version: number,
    exportId: string
  ): Promise<Blob> => {
    const resp = await fetch(
      `${API_URL}/projects/${projectId}/documents/${documentId}/versions/${version}/exports/${exportId}`,
      { headers: devHeaders() }
    );
    if (!resp.ok) throw new Error(`Download failed: ${resp.status}`);
    return resp.blob();
  },

  fetchSubmissions: (projectId: string) =>
    apiFetch(`/projects/${projectId}/submissions/`).then((r) =>
      expectJson<SubmissionResponse[]>(r)
    ),

  createSubmission: (
    projectId: string,
    documentId: string,
    version: number
  ) =>
    apiFetch(
      `/projects/${projectId}/submissions/${documentId}/versions/${version}`,
      { method: "POST" }
    ).then((r) => expectJson<SubmissionResponse>(r)),

  lockSubmission: (projectId: string, submissionId: string) =>
    apiFetch(`/projects/${projectId}/submissions/${submissionId}/lock`, {
      method: "POST",
    }).then((r) => expectJson<SubmissionResponse>(r)),

  approveSubmission: (projectId: string, submissionId: string) =>
    apiFetch(`/projects/${projectId}/submissions/${submissionId}/approve`, {
      method: "POST",
    }).then((r) => expectJson<SubmissionResponse>(r)),

  revokeSubmission: (
    projectId: string,
    submissionId: string,
    reason?: string
  ) => {
    const q = reason ? `?reason=${encodeURIComponent(reason)}` : "";
    return apiFetch(
      `/projects/${projectId}/submissions/${submissionId}/revoke${q}`,
      { method: "POST" }
    ).then((r) => expectJson<SubmissionResponse>(r));
  },

};
