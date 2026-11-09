# Runtime readiness and production architecture proposal

Status: proposal; no cloud resources or customer data were created for this review.
Date: 2026-11-09

## Current deployment boundary

The app is one synchronous Next.js process. `/api/analyze` accepts multipart input, PDF.js parses the complete document, optional local OCR runs as child processes, and model work plus source verification completes before the response stream ends. The browser owns the editable review state. There is no database, durable queue, object store, worker, or cross-instance admission control.

The application accepts a 32 MiB PDF by default outside Vercel, but this is a validation ceiling, not a measured capacity guarantee. The route now caps the entire multipart request at that file limit plus 256 KiB before parsing it. `File.arrayBuffer()` and PDF.js's defensive byte copy still allocate additional memory, and parsing can overlap across requests. Peak RSS and safe request concurrency have not been measured.

Vercel Functions impose a 4.5 MB request/response body limit. A Next.js `serverActions.bodySizeLimit` setting applies to Server Actions, not this Route Handler. A 32 MiB hosted path would need a different flow: authenticated direct-to-object-store upload, an upload-complete API, durable job creation, and worker processing. This introduces storage, queue, and operating costs and requires retention/deletion controls. It is not part of the free MVP.

## Zero-cloud-cost client pilot

For an operator-led pilot using existing equipment, run the app on a customer-controlled machine or private VM with Node.js 22.13+, installed dependencies, and approved model credentials. Keep it bound to loopback or behind the customer's existing authenticated VPN/reverse proxy; do not publish the development server port directly. Use synthetic or customer-authorized non-confidential documents, keep OCR dependencies local, and stop the process after the session. This avoids a new hosting bill; it does not make the model provider free, and it is not a supported multi-user production service.

Before accepting 32 MiB customer PDFs, measure representative text-heavy and image-heavy PDFs at the 32 MiB / 120-page limits, including OCR, cancellation, and two concurrent requests. Record peak process RSS, request duration, outcome, and machine limits. Until those measurements pass with headroom on the actual pilot machine, use smaller files and one operator at a time.

## Suggested production boundaries (future work)

1. **Upload service:** issue an authenticated, short-lived upload session with maximum bytes, MIME/signature checks, checksum, tenant/project ownership, and expiry. Store the immutable original in encrypted object storage; never trust filename or client MIME type.
2. **Job service:** accept an idempotent `analysis_run_id` and immutable `document_version_id`; persist stage/status, attempt, heartbeat, cancellation, deadline, and sanitized error. Enqueue a durable job only after upload checksum verification.
3. **Workers:** separate PDF inventory/OCR and model extraction from the web process. Apply per-tenant and global memory/concurrency limits. Write outputs as versioned artifacts; retries must be idempotent and must not combine partial results into a completed run.
4. **Review API:** persist reviewer edits as append-only `review_action` records against a stable requirement/citation version. A new extraction version must not overwrite or silently revalidate a prior human decision.
5. **Export service:** generate DOCX/XLSX/PDF from an explicit reviewed snapshot and retain the snapshot/version IDs used. Keep UI citations linked to immutable source versions; printed exports omit source page columns per client requirement.

### Phase 1 data contracts

- `Document`: tenant/project owner, original filename (display only), media type, size, SHA-256, created/deleted timestamps.
- `DocumentVersion`: immutable blob reference, parser/OCR settings and version, physical page count, inventory status.
- `PageInventory`: document version, physical page, exact native text, OCR text separately, parser element IDs, geometry, OCR confidence, exact/approximate status, per-region disposition.
- `AnalysisRun`: document version, extractor/model/config version, idempotency key, lifecycle state, stage timestamps, cancellation and sanitized failure reason.
- `RequirementCandidate`: stable run-scoped ID, verbatim source quote, normalized interpretation kept distinct, review state, source inventory IDs, validation disposition.
- `Citation`: document/version, physical page, clause label if known, source text, offsets, parser element IDs, bounding box, OCR confidence, exact/approximate flag. Unknown fields stay null.
- `ReviewAction`: actor, action, before/after value, requirement/citation version, timestamp, reason; append-only.
- `ExportSnapshot`: reviewed requirement IDs and edits, section order, export format/version, creator and timestamp.

The contract deliberately excludes OEM evidence, compliance status, contradiction resolution, and generated clarifications; those are a separately authorized phase.

## Candidate feature fit and reusable interfaces

These are architecture directions only, not approved customer-facing work:

| Candidate | Existing pieces to reuse | Missing boundary / future contract |
| --- | --- | --- |
| Multi-document packages and annexures | `source-document.ts`, sectioned response projection, page citations | Add ordered `DocumentPackage` / `PackageMember` links with explicit attachment/annexure role; every citation keeps its own document-version ID. |
| Eligibility/admin requirements and mandatory-document checklist | Candidate classification, human review states, citation validation | Add typed requirement categories and checklist items with source citation plus pending/received/reviewed state. Keep them separate from technical specifications and never infer legal eligibility. |
| Source-linked evidence and action tracking | Citation model, candidate trace, operator recovery | Add evidence records and append-only actions keyed to requirement/version; do not introduce supplier-compliance status until a separate evidence-assessment contract is approved. |
| Submission-readiness audit | Coverage ledger, unresolved-page diagnostics, reviewed export snapshot | Add deterministic blocking/warning rules over explicitly reviewed checklist and document states; output reasons and cited sources, not a model-generated readiness score. |
| Corrigendum/amendment comparison | Immutable document versions, fingerprints, source inventory | Add parent/supersedes relationships and a version-pair diff artifact; text/page alignment is advisory and every mapped change needs review before replacing an active requirement. |
| Reusable supplier documents | Document/version contract and future tenant boundary | Add tenant-owned library records, access policy, expiry/validity metadata, and explicit selection per tender; never silently reuse stale evidence. |
| Save/resume and document versioning | Existing fingerprints, stable requirement/citation IDs, review actions | Requires persistent transactional metadata plus encrypted object storage. Persist review actions append-only and bind them to immutable extraction/citation versions. |
| Original Word/Excel response-template preservation | Current DOCX/XLSX exporters and section projection | Add format-specific import/export adapters that preserve supported styles, formulas, merged cells, and template anchors. Define a supported-feature contract and fixture-based round-trip tests before claiming fidelity. |

Dependency order: establish identity/version and tenant access boundaries first; then durable upload/run lifecycle and source inventory; then append-only review persistence; then package/checklist/amendment views; then template adapters and audited exports. Readiness audits depend on reviewed, versioned checklist and requirement data. Reusable supplier evidence depends on tenant isolation, retention, and provenance. No new database or queue abstraction belongs in the current single-user app until product owner approval and an actual persistence requirement.

## Migration sequence

1. Measure the synchronous pilot before setting a supported file/concurrency target. Keep the current single-process route for private trials; cap request bodies and fail clearly on limits.
2. Add object storage and upload sessions behind a feature flag. Keep the existing browser-memory flow as a fallback until authenticated upload, expiry, checksum, deletion, and access isolation are verified.
3. Add database tables for documents, versions, runs, inventory, candidates, citations, and review actions. Initially write a shadow copy of new runs; compare IDs/counts/checksums and do not dual-write mutable review state without transactional guarantees.
4. Move parsing and extraction into a durable worker. Run synthetic failure/retry/cancel tests and a representative authorized tender before routing production traffic.
5. Enable persisted review and exports only after tenant isolation, audit logging, retention, backup/restore, and deletion tests pass. There is no existing server-side review history to migrate; browser-memory sessions are ephemeral and should not be implied to be recoverable.

## Deployment decision

There is no verified zero-cost public host in this audit that also provides the required upload/runtime headroom and production reliability. Render Free is 512 MiB / 0.1 CPU and sleeps after inactivity; Oracle Always Free offers up to 2 OCPU / 12 GiB ARM compute but may have no capacity in the home region and account enrollment can require payment details. Neither is a proven fit until architecture compatibility, measured peak memory, cold starts, access control, provider costs, and customer data controls are checked. Vercel remains suitable only for the current small-file demo path, not 32 MiB uploads.

Research is based on current provider documentation checked 2026-11-09:

- [Vercel Functions Limits](https://vercel.com/docs/functions/limitations) documents the 4.5 MB request/response payload and Hobby's 300-second maximum duration.
- [Next.js Server Actions config](https://nextjs.org/docs/app/api-reference/config/next-config-js/serverActions) scopes `bodySizeLimit` to Server Actions.
- [Vercel large-upload guidance](https://vercel.com/kb/guide/how-to-bypass-vercel-body-size-limit-serverless-functions) recommends sending large files to storage from the client.
- [Render Free services](https://render.com/docs/free) says free instances are not for production; [Render compute plans](https://render.com/docs/compute-plans) lists 512 MiB and 0.1 CPU.
- [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) lists 2 OCPU / 12 GiB for Ampere A1 and documents home-region capacity limits; [Oracle account enrollment](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm) says most users need a phone and credit card.
- [Cloud Run quotas](https://docs.cloud.google.com/run/quotas) caps HTTP/1 request size at 32 MiB, leaving less than 32 MiB for a multipart file; [Cloud Billing requirements](https://docs.cloud.google.com/billing/docs) require a valid billing account even for Free Tier use.

## Decisions needed before public client access

- Is the pilot strictly local/private, or does the client require a public URL?
- What is the approved budget for compute, object storage, durable jobs, and model inference?
- What document residency, retention, deletion, and provider data-handling terms apply?
- What file/page size and concurrent operator target must be supported?
- Who owns hosting credentials, incident response, backups, and customer support?
