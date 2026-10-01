# Tender Compliance Engine — Canonical Checkpoint Plan

> **This file is the execution source of truth for building the product from the current repository state to the complete evidence-backed tender compliance workflow.**
>
> Follow the checkpoints in order unless a new requirement, bug, security issue, or architectural fact requires the plan to change. When that happens, update this file in the same PR that changes the direction.

## Current position

Completed checkpoints are crossed out below. The **next implementation checkpoint is CP48 — Phase 1 end-to-end acceptance and release gate**.

The repository has the complete Phase 1 extraction pipeline through CP34 (qualitative normalization and ambiguity escalation), including: real persistence (CP06–CP11), object storage and upload validation (CP12–CP16), document processing state machine and Redis-backed worker (CP17–CP18), source-preserving parsing/rendering/OCR (CP19–CP24), structured extraction schema and LLM adapter through reconciliation/diagnostics (CP25–CP31), the RequirementConstraint model + normalization states (CP32), deterministic numeric/operator/unit parsing (CP33), and qualitative condition extraction with OCR/ambiguity escalation (CP34). The next work is CP35: requirement list/detail API.

## How every human or coding agent must use this file

1. Read `AGENTS.md` first.
2. Read this file and find the first unchecked checkpoint.
3. Work on that checkpoint before jumping ahead unless a discovered dependency forces a plan update.
4. Start from latest `main` and create a focused branch.
5. Open a PR for every change. Never directly commit/push substantive work to `main`.
6. Keep a PR focused on one checkpoint or one coherent sub-part of one checkpoint.
7. Put the checkpoint ID in the PR description and explain why, what changed, scope, provenance/data impact, tests, manual verification, risks, and limitations.
8. Do not mark a checkpoint complete because an interface, mock, table, or stub exists.
9. Complete every item under **This checkpoint is complete only when**.
10. In the same PR that completes a checkpoint: change `[ ]` to `[x]`, strike through the title, change its status to DONE, and optionally add the PR/implementation note.
11. If new work appears, insert it at the correct dependency point instead of silently doing unplanned work.
12. If new information makes part of this plan wrong, update the plan explicitly through a PR.
13. Conservative unresolved states are preferable to fabricated certainty.
14. This file is planning, not implementation evidence. Only shipped/tested code counts.

## Bynd reference reuse policy

The project may use patterns learned from the Bynd repository audit in `docs/BYND-REUSE-AUDIT.md`, but that audit is a reference catalog—not a dependency manifest.

- Reuse architecture ideas, invariants, tests, and interaction patterns only when they fit this product's requirements.
- Do not copy private/unlicensed Bynd source code, proprietary assets, prompts, secrets, deployment identifiers, or internal customer data.
- License-check any repository before copying code. Compatible licenses still require their attribution/notice obligations.
- Do not introduce a private Bynd package/service as a runtime dependency without an explicit ownership/access/product decision.
- Where Tender Compliance has stricter trust rules—especially OCR correction and compliance—the stricter rule wins.
- Prefer fresh implementation behind this repository's adapters over coupling the product to historical experiments.
## Global rules that apply to every checkpoint

- Never fabricate a tender requirement, OEM specification, citation, page, clause, bounding box, evidence item, test result, or compliance status.
- Preserve immutable source versions.
- Preserve provenance through extraction, review, comparison, approval, and export.
- Unknown source metadata stays unknown.
- Ambiguous OCR stays visible and reviewable.
- Missing evidence is not contradictory evidence.
- Human review is a first-class state.
- Deterministic code owns IDs, ordering, hashes, state transitions, lineage, exports, and numerical/unit comparisons.
- LLMs only interpret language inside schema-validated, source-bounded workflows.
- Uploaded documents are hostile/untrusted data and cannot override system/application instructions.
- Every tenant-owned query is organization-scoped and deny-by-default.
- Confidential document bodies do not belong in normal logs.
- Phase 1 must not claim vendor/OEM compliance.
- A feature is done only when persistence, provenance, failure states, tests, truthful UI behavior, and observability exist where relevant.

## End-to-end destination

```text
Create project
  ↓
Upload tender document(s)
  ↓
Immutable source versions
  ↓
Parse pages / render / detect scans / OCR
  ↓
Source-preserving pages
  ↓
Extract explicit technical requirements
  ↓
Validate + anchor every requirement to source
  ↓
Conservative normalization
  ↓
Human review / edit / split / merge / organize
  ↓
Phase 1 matrix + Excel
  ↓
Phase 1 evaluation / security / deployment gate
  ↓
Upload and process OEM/vendor documents
  ↓
Retrieve and review source evidence
  ↓
Extract source-backed vendor specifications
  ↓
Deterministic unit and numeric comparison
  ↓
Evidence-backed qualitative reasoning
  ↓
Conflict / missing evidence / clarification / deviation workflow
  ↓
Human compliance review and approval
  ↓
Final evidence-backed XLSX / DOCX / PDF submission
  ↓
Phase 2 evaluation + production release
```

## Master checklist

### Stage A — Product contract and existing foundation

- [x] ~~CP00 — Product contract and trust rules~~
- [x] ~~CP01 — Repository and application skeleton~~
- [x] ~~CP02 — Local development services~~
- [x] ~~CP03 — CI baseline and API health check~~
- [x] ~~CP04 — Frontend review prototype~~
- [x] ~~CP05 — PR-first engineering workflow~~

### Stage B — Real persistence, tenancy, audit, and projects

- [x] ~~CP06 — Database connection and SQLAlchemy foundation~~
- [x] ~~CP07 — Alembic migrations and schema discipline~~
- [x] ~~CP08 — Organization, identity, authorization, and audit foundation~~
- [x] ~~CP09 — Project model, lifecycle service, and migrations~~
- [x] ~~CP10 — Project API~~
- [x] ✅ ~~CP11 — Real project dashboard and project progress~~
  - Status: DONE — PR #15
  - Branch: `cp11/project-dashboard`

### Stage C — Tender upload, immutable storage, versions, and background jobs

- [x] ✅ ~~CP12 — Object-storage adapter~~
  - Status: DONE — PR #16
  - Branch: `cp12/object-storage-adapter`
- [x] ✅ ~~CP13 — Upload validation and hostile-file controls~~
  - Status: DONE — PR #17
  - Branch: `cp13/upload-validation`
- [x] ✅ ~~CP14 — TenderDocument and immutable DocumentVersion models~~
  - Status: DONE — PR #18
  - Branch: `cp14/document-version-models`
- [x] ✅ ~~CP15 — Tender upload API, versioning, and duplicate semantics~~
  - Status: DONE — PR #19
  - Branch: `cp15/upload-versioning-duplicates`
- [x] ✅ ~~CP16 — Upload UI and document list~~
  - Status: DONE — PR #20
  - Branch: `cp16/upload-ui-document-list`
- [x] ✅ ~~CP17 — Document-processing state machine~~
  - Status: DONE — PR #21
  - Branch: `cp17/document-processing-state-machine`
- [x] ✅ ~~CP18 — Redis-backed worker and idempotent job execution~~
  - Status: DONE — PR #22
  - Branch: `cp18/redis-backed-worker`

### Stage D — Source-preserving parsing, rendering, OCR, and document pages

- [x] ✅ ~~CP19 — PDF parser adapter~~
  - Status: DONE — PR #23
  - Branch: `cp19/pdf-parser-adapter`
- [x] ✅ ~~CP20 — Rendered page assets and real visual source~~
  - Status: DONE — PR #25
  - Branch: `cp20/rendered-page-assets`
- [x] ✅ ~~CP21 — Scanned-page detection and OCR~~
  - Status: DONE — PR #26
  - Branch: `cp21/scanned-page-ocr`
- [x] ✅ ~~CP22 — DOCX adapter and format-appropriate provenance~~
  - Status: DONE — PR #27
  - Branch: `cp22/docx-adapter`
- [x] ✅ ~~CP23 — DocumentPage persistence and structural cleanup~~
  - Status: DONE — PR #28
  - Branch: `cp23/document-page-cleanup`
- [x] ✅ ~~CP24 — Processing retry, idempotency, and partial failure~~
  - Status: DONE — PR #29
  - Branch: `cp24/retry-idempotency`

### Stage E — Conservative technical requirement extraction and provenance

- [x] ✅ ~~CP25 — Structured extraction schema and trusted source-window contract~~
  - Status: DONE — PR #30
  - Branch: `cp25/extraction-schema-boundary`
- [x] ✅ ~~CP26 — LLM extraction adapter, prompt versions, and run metadata~~
  - Status: DONE — PR #31
  - Branch: `cp26/llm-adapter`
- [x] ✅ ~~CP27 — Chunking, overlap, clause hierarchy, tables, and multi-page windows~~
  - Status: DONE — PR #32
  - Branch: `cp27/windowing`
- [x] ✅ ~~CP28 — Requirement candidate extraction, splitting, grouping, and abstention~~
  - Status: DONE — PR #33
  - Branch: `cp28/extraction`
- [x] ✅ ~~CP29 — Duplicate/header/footer/overlap reconciliation~~
  - Status: DONE — PR #34
  - Branch: `cp29/reconciliation`
- [x] ✅ ~~CP30 — Exact/approximate source anchors and Requirement persistence~~
  - Status: DONE — PR #35
  - Branch: `cp30/requirements`
- [x] ✅ ~~CP31 — Extraction diagnostics and reconciliation history~~
  - Status: DONE — PR #36
  - Branch: `cp31/diagnostics`

### Stage F — Conservative normalization and structured constraints

- [x] ✅ ~~CP32 — RequirementConstraint model and normalization states~~
  - Status: DONE — PR #37
  - Branch: `cp32/constraint-model`
- [x] ✅ ~~CP33 — Deterministic numeric/operator/unit parsing~~
  - Status: DONE — PR #39
  - Branch: `cp33/numeric-operator-unit-parsing`
  - Pure regex/rule-based parser. Operators: `=`, `<`, `≤`/`<=`, `>`, `≥`/`>=`, `!=`/`≠`, `between`. Negative numbers, decimals, ranges (5 variants), percentages, units (18 quantity mappings), scientific notation, thousands separators (US/UK/space, European-ambiguous → PARTIAL), tolerances (± N, "tolerance of N"). OCR corruption detected at `_parse_number` level (letter in number token → NEEDS_REVIEW). Scientific notation backtracking guarded by rejecting "e"/"E" as unit in `_SPAN_RE`. Zero fabrication: bare numbers and unit-less ranges yield no constraints.
- [x] ✅ ~~CP34 — Qualitative normalization and ambiguity escalation~~
  - Status: DONE — PR #40
  - Branch: `cp34/qualitative-normalization`
  - New `qualitative.py` module: `parse_qualitative_conditions(fragment, ocr_warning)` extracts explicit qualitative conditions (certifications, IP/NEMA ratings, materials, interfaces, documentation, safety construction, performance) via conservative regex patterns — never infers from vague prose. `conservative_normalized_text()` does whitespace/punctuation-only normalisation (no semantic changes). `NORMALIZATION_VERSION` for rule versioning. Service `normalize_requirement_constraints` now persists numeric + qualitative constraints to `RequirementConstraint` rows, sets `review_state = OCR_WARNING` when `ocr_warning=True`, `NEEDS_CLARIFICATION` when a constraint is NEEDS_REVIEW, and applies conservative normalized text to the requirement. Idempotent: reprocessing replaces existing constraints.

### Stage G — Persistent human review and real source verification

- [x] ✅ ~~CP35 — Requirement list/detail API~~
- [x] ✅ ~~CP36 — Real PDF/source viewer with trustworthy highlights~~
- [x] ✅ ~~CP37 — Wire the three-pane review UI to real APIs~~
- [x] ~~CP38 — Requirement edit and immutable revision history~~
- [x] ~~CP39 — Split, merge, delete/supersede, categories, ordering, mandatory, and notes~~
- [x] ~~CP40 — Review-state machine, audit timeline, and real progress counts~~

### Stage H — Phase 1 matrix and export

- [x] ~~CP41 — Canonical Phase 1 matrix projection and screen~~
- [x] ~~CP42 — XLSX export, history, download, and failure handling~~

### Stage I — Phase 1 evaluation, security, operations, deployment, and release

- [x] ✅ ~~CP43 — Curated Phase 1 benchmark dataset~~
- [x] ✅ ~~CP44 — Automated evaluation harness and quality gates~~
- [x] ✅ ~~CP45 — Adversarial documents, tenant security, upload security, and prompt-injection tests~~
- [x] ✅ ~~CP46 — Observability, performance, resource, cost, retention, backup, and deletion~~
- [x] ✅ ~~CP47 — Deployment configuration and runbook~~
- [ ] CP48 — Phase 1 end-to-end acceptance and release gate

### Stage J — OEM evidence, deterministic comparison, compliance review, and final submissions

- [ ] CP49 — OEM document ingestion and provenance
- [ ] CP50 — Evidence model, retrieval/indexing, and retrieval evaluation
- [ ] CP51 — Evidence review UI and evidence curation
- [ ] CP52 — Vendor specification extraction
- [ ] CP53 — Deterministic unit normalization and specification comparison engine
- [ ] CP54 — ComplianceAssessment model and status semantics
- [ ] CP55 — Evidence-backed qualitative reasoning
- [ ] CP56 — Conflict and contradiction detection
- [ ] CP57 — Missing evidence, clarification questions, and deviations
- [ ] CP58 — Human compliance review and audit
- [ ] CP59 — Final compliance matrix and submission projection
- [ ] CP60 — Final XLSX, DOCX, and PDF outputs
- [ ] CP61 — Approval, locking, submission versions, Phase 2 evaluation, and production release

---

# Stage A — Product contract and existing foundation

What already exists and the rules every later checkpoint must preserve.

## ✅ ~~Checkpoint 00 — Product contract and trust rules~~

**Status:** DONE — already present in the repository.

**Plain-English outcome:** The repository clearly defines what the product does, what Phase 1 is, and what the system must never fabricate.

### What we will do

1. Keep the current PRD, architecture, data model, evaluation, security, roadmap, and engineering rules aligned.
2. Phase 1 remains: tender upload → parsing/OCR → requirement extraction → conservative normalization → human review → matrix → Excel.
3. Vendor/OEM compliance remains outside Phase 1 until the evidence architecture exists.
4. Never fabricate requirements, specifications, citations, pages, clauses, coordinates, evidence, test results, or compliance states.
5. Treat missing evidence, contradictory evidence, and uncertain OCR as different conditions.
6. Use deterministic code for IDs, hashes, ordering, state transitions, lineage, exports, and later numeric/unit comparison.

### How we will verify it

- Docs agree on the same product boundary.
- No current endpoint or UI claims OEM/vendor compliance.

### This checkpoint is complete only when

- A new engineer can explain the intended end-to-end workflow and the trust model from repository docs.

### Guardrail

- Planning text is not proof that a capability is implemented.

## ✅ ~~Checkpoint 01 — Repository and application skeleton~~

**Status:** DONE — already present in the repository.

**Plain-English outcome:** The API, web app, docs, CI, and infrastructure have clear homes.

### What we will do

1. Maintain the monorepo with `apps/api`, `apps/web`, `docs`, `infra`, root tooling, and GitHub workflows.
2. Keep FastAPI and Next.js as the current application foundations.
3. Keep `AGENTS.md` canonical and `CLAUDE.md` linked to it.
4. Use small modules and provider adapters rather than one large service.
5. Keep frontend installs reproducible with the committed lockfile.

### How we will verify it

- Repository tree contains the expected API/web/docs/infra surfaces.
- Frontend and backend dependencies install in CI.

### This checkpoint is complete only when

- A contributor can clone the repository and know where new work belongs.

### Guardrail

- Do not create empty Phase 2 modules or tables just to make the repo look complete.

## ✅ ~~Checkpoint 02 — Local development services~~

**Status:** DONE — already present in the repository.

**Plain-English outcome:** PostgreSQL, Redis, and MinIO are available as the local infrastructure seams.

### What we will do

1. Keep PostgreSQL for relational metadata and audit data.
2. Keep Redis as the queue/broker seam.
3. Keep MinIO as local S3-compatible object storage.
4. Keep local volumes and health checks.
5. Keep local-only credentials out of production configuration.

### How we will verify it

- Docker Compose defines all three services and health checks.
- Environment variable names remain consistent with app configuration.

### This checkpoint is complete only when

- The planned persistence, queue, and object-storage dependencies can be started locally.

### Guardrail

- Do not store real secrets or customer documents in committed fixtures.

## ✅ ~~Checkpoint 03 — CI baseline and API health check~~

**Status:** DONE — already present in the repository.

**Plain-English outcome:** Every PR can be checked automatically before merge.

### What we will do

1. Keep `GET /health`.
2. Keep API lint and tests in CI.
3. Keep frontend typecheck and production build in CI.
4. Run CI on pull requests and on `main`.

### How we will verify it

- API and web jobs pass on a healthy branch.

### This checkpoint is complete only when

- A test/type/build regression is visible before merge.

### Guardrail

- A health endpoint only proves the API process boots; it does not prove the real product pipeline exists.

## ✅ ~~Checkpoint 04 — Frontend review prototype~~

**Status:** DONE — already present in the repository.

**Plain-English outcome:** The product has a clear visual target for project and requirement review.

### What we will do

1. Keep the compact app shell and project dashboard.
2. Keep the three-pane review workspace: requirements, source, review/evidence.
3. Keep search, filters, review navigation, source chips/popovers, source highlighting, OCR warning, edit, notes, and mark-reviewed/reopen interactions.
4. Keep demo/local state explicitly labeled until replaced by APIs.
5. Preserve the quiet enterprise visual system while backend work lands.

### How we will verify it

- Dashboard and demo review workspace render and interact.
- No vendor-compliance verdicts appear in the Phase 1 prototype.

### This checkpoint is complete only when

- The intended user workflow is visually understandable and ready to be connected to real data.

### Guardrail

- Do not spend the next milestones redesigning the prototype instead of building the real data path.

## ✅ ~~Checkpoint 05 — PR-first engineering workflow~~

**Status:** DONE — already present in the repository.

**Plain-English outcome:** Every meaningful change is made on a branch, reviewed in a PR, checked by CI, and then merged.

### What we will do

1. Start every change from current `main`.
2. Create a focused branch.
3. Never commit/push a feature, fix, docs change, migration, config change, or refactor directly to `main`.
4. Write a meaningful PR description with why/what/scope/provenance/data impact/tests/manual verification/risks.
5. Merge only after relevant CI is green.
6. Prefer squash merge.

### How we will verify it

- `AGENTS.md` and PR template state these rules.
- Recent planned changes are represented by PRs.

### This checkpoint is complete only when

- Any agent can follow the repository workflow without needing verbal instructions.

### Guardrail

- Do not create empty or artificial PRs.

# Stage B — Real persistence, tenancy, audit, and projects

Turn the static skeleton into a durable multi-tenant application where real projects survive refresh/restart.

## ✅ ~~Checkpoint 06 — Database connection and SQLAlchemy foundation~~

**Status:** DONE — implemented and tested.

**Plain-English outcome:** FastAPI can use PostgreSQL through a clean persistence layer.

### What we will do

1. Add database URL/settings to configuration.
2. Use SQLAlchemy 2.x unless a new explicit architecture decision replaces it.
3. Create engine/session factories outside routes.
4. Inject sessions into application services.
5. Add a test-database strategy.
6. Fail clearly on invalid database configuration.

### How we will verify it

- Tests can open/close a session.
- No route owns raw DB connection setup.

### This checkpoint is complete only when

- Application services can persist data through a reusable session boundary.

### Bynd reuse notes

- **Reference:** `Bynd-ai/company-reports-backend/app/db/session.py` demonstrates a clean async SQLAlchemy/SQLModel session boundary. Reuse the architecture idea, not the file.
- Prefer an async engine/session if our FastAPI request path benefits from it; keep the choice explicit rather than copying a framework default.
- Do **not** copy its `metadata.create_all()` startup behavior into production. Our schema source of truth remains Alembic.

### Guardrail

- Do not create every future table in this checkpoint.

### Implementation / PR note

- **Branch:** `cp06/database-sqlalchemy-foundation`
- **Files:** `pyproject.toml`, `src/tender_compliance_api/db/__init__.py`,
  `src/tender_compliance_api/db/session.py`, `src/tender_compliance_api/config.py`,
  `src/tender_compliance_api/main.py`, `tests/conftest.py`, `tests/test_db.py`,
  `.env.example`.
- **Async engine decision:** Declared `sqlalchemy[asyncio]` (rather than
  `sqlalchemy`) plus the `asyncpg` driver. The `[asyncio]` extra pulls in
  `greenlet` — required by SQLAlchemy's asyncio extension at runtime — and
  `DATABASE_URL` in `.env.example` uses the `postgresql+asyncpg://` scheme to
  match. This is an explicit async-first choice, not a framework default.
- **Lifecycle:** `main.py` gained an `asynccontextmanager` lifespan that calls
  `init_engine()` on startup (only when `DATABASE_URL` is set) and `close_engine()`
  on shutdown. No route constructs its own engine/session.
- **Test strategy:** `conftest.py` installs a session-scoped autouse fixture that
  initializes an in-memory `sqlite+aiosqlite` engine (via `StaticPool`) so the test
  suite is self-contained and does not require Postgres.
- **Verified behaviors:**
  - `init_engine("")` raises `ValueError` (clear configuration failure).
  - `get_session()` yields a real `AsyncSession` through which a query can run.
  - `get_session()` raises `RuntimeError` when the engine is uninitialized.
  - On context exit, the transaction is cleanly closed (verified via
    `in_transaction()`, since SQLAlchemy 2.0+ `Session.is_active` only tracks
    partial-rollback state, not open/closed state).
  - `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass.


## ✅ ~~Checkpoint 07 — Alembic migrations and schema discipline~~

**Status:** DONE — implemented and tested.

**Plain-English outcome:** Every database change can be reproduced from an empty database.

### What we will do

1. Add Alembic tied to application metadata.
2. Create the migration directory/config.
3. Create the initial migration baseline.
4. Document upgrade/downgrade/current/history commands.
5. Add a migration smoke test or CI check.
6. Require later schema changes to ship as new migrations.

### How we will verify it

- `alembic upgrade head` works against a fresh database.
- Migration history is deterministic.

### This checkpoint is complete only when

- No developer needs to manually create tables.

### Bynd reuse notes

- **Reference:** `Bynd-ai/bynd-devops-system/docs/migrations-and-seeding.md`.
- Treat migrations as an explicit deployment step: **migrate before the new image is deployed**.
- Never run production migrations automatically during application startup; multiple replicas can race and a failed migration can break every boot.
- If production Postgres is private/VNet-only, run migrations as a one-off job inside that environment instead of weakening database network controls for CI.

### Guardrail

- Do not rewrite released migrations casually.

### Implementation / PR note

- **Branch:** `cp07/alembic-migrations`
- **Dependency:** Added `alembic>=1.13,<2.0` to runtime dependencies (needed for
  deploy-time migrate jobs and the CI smoke test).
- **Files:** `pyproject.toml`, `src/tender_compliance_api/db/base.py`,
  `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`,
  `alembic/versions/0001_initial_baseline.py`, `tests/test_migration.py`, `Makefile`.
- **Design:** `env.py` is async-aware (`async_engine_from_config` + `asyncio.run`) and
  tied to `Base.metadata` from `db/base.py` (the single declarative registry). The
  database URL resolves from the Alembic config (test/CLI override) first, then the
  `DATABASE_URL` application setting; it refuses to proceed if neither is set.
- **Baseline:** The initial migration (`0001_initial_baseline`) is intentionally
  empty — it creates no application tables, only Alembic's version-tracking. First
  real tables arrive in CP08+.
- **Commands documented** via Makefile: `api-migrate` (upgrade head),
  `api-migrate-down` (downgrade -1), `api-migrate-new` (revision).
- **Verified:** `alembic upgrade head`, `alembic current`, `alembic history`, and
  `alembic downgrade -1` all succeed against a fresh SQLite DB; `get_heads()` returns a
  single deterministic head; pytest smoke tests pass (upgrade, version check, head
  count, and upgrade→downgrade→upgrade roundtrip).

## ✅ ~~Checkpoint 08 — Organization, identity, authorization, and audit foundation~~

**Status:** DONE — PR #12.

**Plain-English outcome:** Every tenant-owned action knows who the actor is and which organization owns the data.

### What we will do

1. Add `Organization` and product-relevant user/membership records.
2. Create an auth/request-context boundary that resolves actor ID, organization ID, and permissions.
3. Support a clearly development-only local identity mode.
4. Deny protected requests without a valid actor.
5. Scope every tenant query by organization.
6. Add `AuditLog` with actor/action/entity/project/minimal metadata/timestamp.
7. Create a reusable audit service.
8. Write cross-tenant denial tests before project/document APIs expand.

### How we will verify it

- Org A cannot read/write Org B records even with guessed UUIDs.
- Audit events are organization-scoped and avoid confidential bodies.

### This checkpoint is complete only when

- There is one reusable authorization context and one audit path for later services.

### Bynd reuse notes

- **References:** `Bynd-ai/company-reports-backend` organization/membership/auth services and `Bynd-ai/universal-auth-service`.
- Reuse the tenant pattern: explicit membership rows, uniqueness on `(organization_id, user_id)`, constrained roles, and provider-identity consistency checks.
- At the web/auth boundary add request IDs, production-vs-development origin separation, redirect allowlisting, route-appropriate rate limiting, and security headers/CSP.
- Keep our own provider-neutral auth boundary; do not couple this repo to Bynd's deployed auth service or private configuration.

### Guardrail

- Never trust an organization ID supplied by the browser without verifying membership.

**Implementation note (PR #12):** Added `Organization`, `User`, `Membership`, and `AuditLog` models (`db/models.py`) via Alembic migration `0002_organization_identity_audit`. Auth boundary lives in `auth/` (`AuthContext`, `resolve_auth_context` dev-mode resolver, `get_auth_context` FastAPI dependency — deny-by-default 401). Audit path in `audit/` (`AuditService` + `write_audit_event`). Dev identity mode reads `X-Dev-User-Id` / `X-Dev-Organization-Id` headers, auto-creates User/Organization but verifies Membership (no auto-membership). Tests use file-based SQLite with `alembic upgrade head` so the real migration schema is exercised. `project_id` on AuditLog is deferred to CP09 (no Project table yet).## ✅ ~~Checkpoint 09 — Project model, lifecycle service, and migrations~~

**Status:** DONE — PR #13.

**Plain-English outcome:** A tender-response workspace becomes a real persisted entity.

### What we will do

1. Add `Project` with UUID, organization, name, optional external tender ID, status, creator, timestamps.
2. Define workflow statuses that describe processing/review progress, not vendor compliance.
3. Create service methods for create/get/list/rename/archive/reopen.
4. Guard impossible lifecycle transitions.
5. Write audit events for mutations.
6. Index organization/status lookups.

### How we will verify it

- Service tests cover lifecycle transitions and tenant isolation.
- Projects survive restart.

### This checkpoint is complete only when

- Project business rules live in services/domain code, not scattered across routes.

### Guardrail

- Do not encode compliance meaning into project status.

**Implementation note (PR #13):** Added `Project` model and `ProjectStatus` enum (`db/models.py`; `str`/enum.StrEnum stored via `sa.Enum`). Workflow statuses (`draft`, `tender_uploaded`, `documents_processing`, `requirements_extracted`, `review_in_progress`, `matrix_ready`, `exported`, `archived`) describe processing/review progress only — not vendor compliance. Added `project_id` (nullable FK) to `AuditLog`. Created `project/` package with `ProjectService` (create/get/list/rename/archive/reopen), tenant-scoped via `AuthContext.organization_id`, with lifecycle guards (`ProjectArchivedError`, `StateTransitionError`). `index=True` on `Project.organization_id` plus composite `ix_projects_org_status` index. Migration `0003_project_model` is hand-written (autogenerate produced false-positive UUID type changes from SQLite's NUMERIC affinity). `audit_logs.project_id` added via `batch_alter_table` (SQLite limitation). `session_cm` fixture added to conftest.py. Tests use file-based SQLite with `alembic upgrade head`.

## ✅ ~~Checkpoint 10 — Project API~~

**Status:** DONE — PR #14.

**Plain-English outcome:** A client can perform the complete project lifecycle through supported API behavior.

### What we will do

1. Add `POST /projects`.
2. Add `GET /projects`.
3. Add `GET /projects/{id}`.
4. Add rename/update plus archive/reopen actions.
5. Return stable response schemas.
6. Return explicit 400/403/404 errors.
7. Paginate/list deterministically where needed.

### How we will verify it

- API tests cover happy paths, validation, missing records, and cross-tenant access.

### This checkpoint is complete only when

- A client can perform the complete project lifecycle through supported API behavior.

### Guardrail

- Do not expose an endpoint before its backing service behavior exists.

**Implementation note (PR #14):** Added `ProjectCreate`, `ProjectRename`, and `ProjectResponse` Pydantic schemas (with `ConfigDict(from_attributes=True)`) in `routes/projects.py`. Routes: `POST /projects` (201), `GET /projects`, `GET /projects/{id}`, `PATCH /projects/{id}` (rename), `POST /projects/{id}/archive`, `POST /projects/{id}/reopen`. All routes use `Depends(get_auth_context)` (deny-by-default 401) and `Depends(get_session)` for the session, delegating to `ProjectService`. Domain errors (`ProjectNotFoundError` → 404, `ProjectArchivedError`/`StateTransitionError` → 400) are mapped via an inline `_to_http` helper and `except _ProjectErrors` blocks. Mutating routes call `session.refresh(project)` before `model_validate` to avoid SQLAlchemy async-lazy-load errors on server-defaulted columns (e.g. `updated_at`), then `session.commit()`. Router registered in `main.py`. API tests (18 tests) cover create/list/get/rename/archive/reopen, auth-required, validation (422), not-found (404), cross-tenant (404), state-transition guards (400), and audit events.

## ✅ ~~Checkpoint 11 — Real project dashboard and project progress~~

**Status:** DONE — PR #15

**Plain-English outcome:** Hard-coded dashboard data is replaced by persisted projects and trustworthy workflow summaries.

### What we did

1. Created `lib/api/client.ts` — typed `fetch` wrapper with dev identity headers.
2. Rewrote `app/page.tsx` as a `"use client"` component that loads projects from `GET /projects`, shows loading/empty/error states, connects 'New tender' and 'Create tender project' card to `POST /projects`, links cards to `/projects/{id}`, and renders status pills + updated-at from real data.
3. Created `app/projects/[id]/page.tsx` — project detail page with inline rename, archive/reopen buttons, back-to-dashboard link, and detail panel showing persisted fields.
4. Added `.env.local.example` for `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_DEV_USER_ID`, `NEXT_PUBLIC_DEV_ORG_ID`.
5. Added CSS for `.status-neutral`, `.empty-state`, `.dialog`, `.detail-panel`, `.project-card-archived`.

### How we verified it

- `npm run typecheck` (strict mode) ✅
- `npm run build` ✅ (5 routes prerendered/static, `/projects/[id]` dynamic)
- API tests: 60/60 pass
- Summary strip shows real active-tenders count; `—` for document/requirement/review counts (not yet available)
- No hardcoded project data remains in the dashboard

# Stage C — Tender upload, immutable storage, versions, and background jobs

Accept real tender files safely and create the processing handoff without doing heavy work inside HTTP requests.

## ✅ ~~Checkpoint 12 — Object-storage adapter~~

**Status:** DONE — PR #16

**Plain-English outcome:** Original/derived files are stored outside PostgreSQL behind a provider-agnostic interface.

### What we did

1. Defined abstract `ObjectStorageAdapter` interface with `put`/`get`/`head`/`delete`/`read_access` operations and `ObjectInfo` dataclass.
2. Implemented `S3StorageAdapter` (boto3) with MinIO-compatible S3 endpoint — all boto3 calls confined to this module.
3. Implemented `FakeStorageAdapter` (in-memory) for tests with no external dependencies.
4. Added `build_key()` key-scoping: `{org_id}/{project_id}[/{document_id}[/{version}]]/{uuid}{ext}` — org_id first guarantees namespace isolation.
5. Added `StoredObject` model in PostgreSQL for object metadata (checksums, key, filename, content-type, etag) — never raw file bytes.
6. SHA-256 checksums computed application-side, never trusted from provider.

### How we verified it

- `ruff check .` ✅, `mypy src/` ✅ (23 source files)
- `alembic upgrade head` ✅ (0001→0004)
- 13 new tests in `tests/test_storage.py` + 60 existing = 73 pass
- Round-trip: put→get returns identical bytes
- Checksum: SHA-256 matches `hashlib.sha256(data).hexdigest()`
- Org isolation: keys with different org_id prefixes never collide

### This checkpoint is complete only when

- Application services do not call MinIO/S3 SDKs directly.

### Guardrail

- Storage paths are not a substitute for authorization.

## ✅ ~~Checkpoint 13 — Upload validation and hostile-file controls~~

**Status:** DONE — PR #17

**Plain-English outcome:** Unsafe, unsupported, or unreadable files are rejected before parsing.

### What we did

1. Created `validation/` package:
   - `models.py` — `FileFormat` enum, `ValidationResult` dataclass, `FileValidationError`, magic-byte/MIME/extension maps
   - `rules.py` — `ExtensionRule`, `FileSignatureRule`, `FileSizeRule` (abstract `FileValidationRule` base)
   - `pdf.py` — `PdfValidationRule` using `pypdf` to detect malformed PDFs, password protection, and excessive page counts
   - `service.py` — `ValidationService` orchestrates all rules and infers format from file signature (not browser MIME)
2. Created `scan/` package:
   - `adapter.py` — Abstract `MalwareScanner` + `ScanResult`
   - `fake.py` — `FakeScanner` with `TEST_INFECTED_SIGNATURE` for test malware detection
3. Created `POST /projects/{project_id}/upload` route that validates → scans → stores → creates StoredObject → transitions project to TENDER_UPLOADED → audits
4. Added `ProjectService.mark_uploaded()` for DRAFT→TENDER_UPLOADED transition
5. Added `pypdf>=4.0,<5.0` and `python-multipart>=0.0.12,<1.0` dependencies
6. Storage/scanner dependencies injected via FastAPI (overridable in tests)

### How we verified it

- `ruff check .` ✅, `mypy src/` ✅ (32 source files)
- `alembic upgrade head` ✅ (0001→0004)
- 27 new tests: 10 validation + 7 upload endpoint + 10 existing = 90 total pass
- Rejected files return 422 with explicit error reasons
- Audit events logged for rejected uploads
- Cross-tenant access denied (404)
- PDF JavaScript/macros never executed — pypdf only reads structural metadata

## ✅ ~~Checkpoint 14 — TenderDocument and immutable DocumentVersion models~~

**Status:** DONE — PR #18

**Plain-English outcome:** Every citation can target one exact uploaded source version.

### What we did

1. Added `DocumentProcessingStatus` enum (`uploaded`, `processing`, `parsed`, `failed`).
2. Added `TenderDocumentType` enum (`tender`, `amendment`, `specification`, `other`).
3. Added `TenderDocument` model: linked to project, `display_name`, `document_type`, timestamps.
4. Added `DocumentVersion` model: immutable, versioned, with `stored_object_id` FK to `StoredObject` (ON DELETE RESTRICT), `sha256`, `mime_type`, `size_bytes`, `processing_status`, `parser_name/version`, `ocr_name/version`, timestamps.
5. Enforced unique `(document_id, version_number)` constraint.
6. Added lookup indexes on `document_id`, `stored_object_id`, and `project_id`.
7. Created hand-written Alembic migration `0005_document_version`.
8. Exported new models from `db/__init__.py`.

### How we verified it

- `ruff check .` ✅, `mypy src/` ✅ (32 source files)
- `alembic upgrade head` ✅ (0001→0005)
- 6 new tests in `test_document_models.py`:
  - TenderDocument creation + defaults
  - DocumentVersion v1 creation + defaults (processing_status=UPLOADED)
  - Later version creates new row, old version stays queryable
  - Duplicate version_number violates unique constraint
  - FK introspection (RESTRICT on stored_object_id, CASCADE on document_id)
- 96 tests total pass

## ✅ ~~Checkpoint 15 — Tender upload API, versioning, and duplicate semantics~~

**Status:** DONE — PR #19

**Plain-English outcome:** A project can receive real tender bytes and get durable document/version IDs.

### What we did

1. Upgraded `POST /projects/{id}/upload` to create `TenderDocument` + `DocumentVersion` records alongside the existing `StoredObject`.
2. Added SHA-256 computation before storage for duplicate detection.
3. Duplicate-content handling: if a `StoredObject` with the same SHA-256 exists for the org, the bytes are **reused** (no re-storage) and a new `DocumentVersion` is created on the same `TenderDocument` with `version_number = max + 1`.
4. New-content handling: if no existing document for the project, creates a new `TenderDocument` + `DocumentVersion` v1.
5. Updated `UploadResponse` schema to include `document_id` and `version_number`.
6. Updated `build_key` calls to include `document_id` and `version` in the storage path.
7. Audit events now include `document_id`, `version_number`, and `bytes_reused` metadata.
8. Project status transitions: DRAFT→TENDER_UPLOADED on first upload; subsequent uploads (already TENDER_UPLOADED) are logged but don't fail.

### How we verified it

- `ruff check .` ✅, `mypy src/` ✅ (32 source files)
- `alembic upgrade head` ✅ (0001→0005)
- 99 tests pass (3 new in test_uploads.py: duplicate content reuse, different content new version, durability after restart)
- Existing 7 upload tests still pass (updated to check for `document_id` + `version_number`)
- Duplicate upload: same stored_object_id, version_number=2, same document_id
- Different content: new stored_object_id, version_number=2, same document_id
- Upload survives across session boundaries (file-based SQLite durability)

### Guardrail

- Do not parse/extract synchronously inside the upload request — only validation + storage + metadata persistence.

## ⬜ Checkpoint 16 — Upload UI and document list

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Users can add a real tender and understand what was accepted.

### What we will do

1. Add Documents/upload UI to a real project.
2. Support drag/drop and file chooser.
3. Show filename, version, size, upload status, and explicit errors.
4. List persisted documents/versions.
5. Refresh using returned IDs.
6. Avoid fake progress percentages.

### How we will verify it

- Upload → refresh → document remains listed.
- Invalid files show specific user-facing errors.

### This checkpoint is complete only when

- A user can create a project and attach a real tender without developer tools.

### Guardrail

- Do not suppress server-side validation errors.

## ✅ ~~Checkpoint 17 — Document-processing state machine~~

**Status:** DONE — PR #21

**Plain-English outcome:** The product can always explain where an uploaded version is in processing.

### What we will do

1. Define states such as UPLOADED/QUEUED/PROCESSING/PARTIAL/READY/FAILED with final names documented.
2. Track current stage and failure reason separately.
3. Record timestamps and retry/attempt counts.
4. Guard invalid transitions.
5. Expose processing status API.
6. Derive project workflow status from document state where appropriate.

### How we will verify it

- Impossible transitions fail tests.
- Page/worker failure does not look like successful empty output.

### This checkpoint is complete only when

- Users/operators can tell whether processing is queued, running, partial, ready, failed, or retryable.

### Guardrail

- Never promote partial processing to READY without an explicit policy.

### Implementation / PR note

- **Branch:** `cp17/document-processing-state-machine`
- **Extended `DocumentProcessingStatus` enum** (`db/models.py`): Added `QUEUED` ("queued") and `PARTIAL` ("partial"). Kept existing `UPLOADED`, `PROCESSING`, `PARSED`, `FAILED`. Final documented states: `uploaded` → `queued` → `processing` → `parsed` / `partial` / `failed`; `partial` and `failed` can retry back to `queued`.
- **Added `ProcessingStage` enum** (`parse`, `ocr`, `cleanup`, `extract`) and `RunStatus` enum** (`started`, `running`, `completed`, `failed`, `retry`).
- **Added `ProcessingRun` model**: tracks per-stage processing attempts with `run_id` (correlation), `attempt`, `stage`, `status`, `error_type`, `error_message`, `started_at`, `completed_at`. FK to `DocumentVersion` with `ON DELETE CASCADE`.
- **Created `document/` service package** with `DocumentService`:
  - `transition_to()` — guards invalid state transitions via `_ALLOWED_TRANSITIONS` map.
  - `begin_run()` / `complete_run()` — creates and resolves `ProcessingRun` rows, automatically transitions `QUEUED` → `PROCESSING` when a worker picks up a job.
  - `_reconcile_version_status()` — derives `DocumentVersion.processing_status` from the aggregate of all `ProcessingRun` rows using conservative rules: all stages completed → `PARSED`; some completed + some permanently failed → `PARTIAL`; all permanently failed → `FAILED`; any stage still running → stays `PROCESSING`; unattempted stages prevent premature promotion. Retry budget: max 5 attempts per stage.
  - `get_version_or_raise()` / `get_runs()` / `list_project_versions()` — tenant-scoped queries.
  - `_safe_transition()` — used during reconciliation to avoid raising on already-terminal states.
- **Extended `DocumentVersionResponse`** with `parser_name`, `parser_version`, `ocr_name`, `ocr_version` fields.
- **Added API endpoints:**
  - `GET /projects/{id}/documents/{doc_id}/versions/{v}` — returns version detail with processing status.
  - `GET /projects/{id}/documents/{doc_id}/versions/{v}/runs` — returns processing runs for a version.
  - Both enforce org isolation (cross-tenant → 404).
- **Migration `0006_processing_run`**: Creates `processing_stage` and `run_status` enums, `processing_runs` table (with indexes on `document_version_id`, `(document_version_id, stage)`, and `run_id`), and extends `doc_processing_status` enum with `queued`/`partial` (PostgreSQL `ALTER TYPE ADD VALUE`; SQLite stores enums as VARCHAR so no change needed). Downgrade drops the table and new enums but intentionally keeps the extended `doc_processing_status` values (PostgreSQL cannot drop enum values).
- **Tests:** 23 new tests in `tests/test_document_processing.py`:
  - 10 state-machine guard tests (valid + invalid transitions).
  - 1 enum persistence test (QUEUED + PARTIAL round-trip).
  - 3 service transition tests (valid, invalid-blocked, terminal-blocked).
  - 3 ProcessingRun lifecycle + reconciliation tests (all stages complete → PARSED; some fail permanently → PARTIAL; all fail → FAILED).
  - 4 API tests for `GET /documents/{doc_id}/versions/{v}` (found, not-found, cross-tenant, wrong-project).
  - 2 API tests for `GET .../runs` (list runs, cross-tenant denied).
  - 1 test verifying `GET /documents` shows correct processing status after upload.
- **Verified:** `ruff check .` ✅, `mypy src/` ✅ (34 source files), `alembic upgrade head` ✅ (0001→0006), `pytest` ✅ (124 tests = 101 prior + 23 new).

## ✅ ~~Checkpoint 18 — Redis-backed worker and idempotent job execution~~

**Status:** DONE — PR #22

**Plain-English outcome:** Parsing/extraction runs in a background worker instead of blocking API requests.

### What we will do

1. Define a job-runner interface.
2. Use a small Redis-backed queue implementation.
3. Create a worker entrypoint.
4. Put identifiers—not full confidential document bodies—on the queue.
5. Add correlation/job IDs.
6. Add bounded retries.
7. Make processing safe to retry.
8. Record permanent vs retryable failures.

### How we will verify it

- Upload/enqueue returns promptly.
- Worker retry does not duplicate final page/requirement state.

### This checkpoint is complete only when

- Background processing can be tested independently of FastAPI.

### Bynd reuse notes

- **References:** `Bynd-ai/final-final-chunking-pipeline`, `metric-search-backend`, and `finance-data-ingestion-service`.
- Model one document-version processing request as one durable job identity. Use bounded worker concurrency/prefetch so one worker does not reserve many expensive documents at once.
- Carry the same `job_id` / correlation ID through API acceptance, queue wait, worker stages, provider calls, persistence, and final state.
- Give retries an explicit budget and classify retryable vs permanent provider failures; never retry forever.
- Record per-stage timings so parsing/OCR/model/persistence bottlenecks can be diagnosed independently.

### Guardrail

- Do not introduce agents or complex distributed orchestration.

### Implementation / PR note

- **Branch:** `cp18/redis-backed-worker`
- **Queue adapter package** (`tender_compliance_api/queue/`):
  - `adapter.py` — abstract `QueueAdapter` with `enqueue`/`dequeue`/`acknowledge`/`release`/`size`. `QueueMessage` dataclass carries only identifiers (document_version_id, document_id, organization_id, version_number, stage, run_id, attempt) — never document bodies. `make_job_id()` generates a deterministic UUID5 from (version_id, stage) for idempotency. `QueuedJob` dataclass returned by `dequeue`.
  - `fake.py` — `FakeQueueAdapter` in-memory implementation for tests. Honors `delay` by tracking `released_at` timestamp; supports idempotent enqueue (same job_id not duplicated).
  - `redis.py` — `RedisQueueAdapter` using Redis LIST for job queue (`LPUSH`/`BRPOP` with 5s poll timeout), HASH for job metadata, and a short-lived `SET NX` lock with TTL for claiming (visibility timeout). Idempotent enqueue: checks job existence + claim key before pushing.
- **DocumentService.enqueue_processing()** (CP17, extended in CP18): Transitions version `UPLOADED → QUEUED`, returns a deterministic `run_id` (UUID5 from version_id + PARSE stage). Idempotent: if version is already `QUEUED`/`PROCESSING`, returns the same run_id without re-transitioning.
- **Upload route** (`POST /projects/{id}/upload`): After creating the `DocumentVersion` (status=UPLOADED) and committing, calls `enqueue_processing` to transition to QUEUED, then enqueues a job via `QueueAdapter.enqueue()`. The `QueueAdapter` is injected as a FastAPI dependency (`get_queue_adapter`), overridable in tests. Returns 201 promptly — no blocking processing.
- **Worker package** (`tender_compliance_worker/`):
  - `processor.py` — `JobProcessor` class: processes a `QueuedJob` by calling `DocumentService.begin_run` (QUEUED→PROCESSING) for each stage, then `complete_run` for each stage. Placeholder pass marks all 4 stages (PARSE, OCR, CLEANUP, EXTRACT) as COMPLETED → PARSED. Idempotent: skips already-terminal versions. `record_failure()` function records permanent failures on the ProcessingRun.
  - `worker.py` — `Worker` class: `run_once()` dequeues up to `max_concurrency` jobs (default 4), processes concurrently via `asyncio.gather`, acknowledges successes, and handles failures (re-enqueue with exponential backoff for retries < MAX_RETRIES=5; `record_failure` + acknowledge for permanent failures). `create_worker()` factory selects `RedisQueueAdapter` when `REDIS_URL` is set, falls back to `FakeQueueAdapter`. `main()` CLI entry point with `--max-concurrency` and `--queue` args.
  - `__main__.py` — enables `python -m tender_compliance_worker`.
- **Config** (`config.py`): Added `redis_url: str = ""` setting and `max_retries: int = 5`, `max_concurrency: int = 4`.
- **Package config** (`pyproject.toml`): Added `redis>=5.0,<6.0` dependency, `tender_compliance_worker` to wheel packages, and `tender-worker` console script entry point.
- **Frontend** (`lib/api/client.ts`): Added `"queued"` and `"partial"` to `DocumentProcessingStatus` type; added `parser_name`/`parser_version`/`ocr_name`/`ocr_version` to `DocumentItem`.
- **Tests:** 14 new tests in `tests/test_worker.py`:
  - 6 `FakeQueueAdapter` tests (enqueue/dequeue, empty dequeue, acknowledge, release, delay, idempotent enqueue).
  - 3 `make_job_id` tests (determinism, different version, different stage).
  - 2 `JobProcessor` tests (process → PARSED with 4 runs, idempotent skip terminal).
  - 2 `Worker.run_once` tests (processes queued job, empty queue returns 0).
  - 1 full integration test (upload → auto-enqueue → worker → PARSED).
- **Verified:** `ruff check .` ✅, `mypy src/` ✅ (42 source files), `alembic upgrade head` ✅ (no new migration needed — CP18 is queue/worker infrastructure only), `pytest` ✅ (138 tests = 124 prior + 14 new). Web: `npm run typecheck` ✅, `npm run build` ✅.

# Stage D — Source-preserving parsing, rendering, OCR, and document pages

Turn source files into trustworthy page/segment representations while keeping uncertainty visible.

## ✅ Checkpoint 19 — PDF parser adapter

**Status:** COMPLETE via PR (squash-merged to main).

**Plain-English outcome:** Digitally generated PDFs produce page-scoped text behind a replaceable parser interface.

### What we did

1. Defined parser input/output contracts (`PageResult`, `ParseResult`).
2. Used `pypdf` (already a dependency) for the PDF parser implementation.
3. Preserved page number/order via 1-indexed `page_number` on each `PageResult`.
4. Returned page-level warnings/errors (e.g. "page has no text layer").
5. Recorded parser name/version from the adapter (`parser.name`/`parser.version`).
6. Never collapsed all pages into one untraceable text blob — each page is a separate `DocumentPage` row.

### How we verified it

- Digital fixtures return correct page counts/order/text (8 parser unit tests).
- Malformed PDFs produce explicit `fatal_error` (3 integration tests).
- Encrypted PDFs produce `fatal_error` with "password" message.
- Scanned (blank) pages are flagged `ocr_needed=True` → version stays PARTIAL.
- Worker stores `DocumentPage` rows with text, page numbers, and `ocr_needed` flags.
- Migration `0007_document_page` creates `document_pages` table.

### This checkpoint is complete

- [x] Parser adapter interface (`ParserAdapter` ABC) exists in `tender_compliance_api/parser/`.
- [x] `PypdfParserAdapter` extracts per-page text (never collapsed to one blob).
- [x] Page-level warnings/errors are returned.
- [x] Parser name/version is recorded on `DocumentVersion`.
- [x] `DocumentPage` model stores parsed pages with page identity.
- [x] Worker integrates the parser in the PARSE stage (`_do_parse` reads bytes from storage, parses, stores pages).
- [x] Malformed PDFs produce explicit failure (PARSE run FAILED, version QUEUED for retry).
- [x] Scanned PDFs (no native text) flag `ocr_needed=True`, version → PARTIAL.
- [x] `_ALLOWED_TRANSITIONS` includes `PROCESSING → QUEUED` for retryable failures.
- [x] Migration `0007_document_page` + `test_migration.py` updated.
- [x] `ruff check .` ✅, `mypy src/` ✅, `alembic upgrade head` ✅, `pytest` ✅ (151 tests).

### Implementation notes

- `tender_compliance_api/parser/adapter.py` — abstract `ParserAdapter` with `ParseResult`/`PageResult` dataclasses.
- `tender_compliance_api/parser/pypdf.py` — production parser using `pypdf.PdfReader`. Detects encryption, missing text layers, and short-text pages.
- `tender_compliance_api/parser/fake.py` — deterministic fake for tests.
- `db/models.py` — `DocumentPage` model (page_number, extracted_text, ocr_needed, structural_metadata).
- `document/service.py` — `get_stored_object_key()` and `store_pages()` methods; `_reconcile_version_status` checks `ocr_needed` pages to transition to PARTIAL.
- `tender_compliance_worker/processor.py` — `JobProcessor` accepts `parser` + `storage` adapters; PARSE stage calls `_do_parse`; PARSE failure skips remaining stages and records parser identity.

### Guardrail

- [x] Page boundaries preserved — each PDF page maps to exactly one `DocumentPage` row, ordered by `page_number`.

## ✅ Checkpoint 20 — Rendered page assets and real visual source

**Status:** DONE — PR #25

**Plain-English outcome:** Every PDF page has a visual representation reviewers can inspect, stored as derived PNG assets keyed to the source version.

### What we did

1. Added a replaceable `RendererAdapter` port (`tender_compliance_api/renderer/`) mirroring the `ParserAdapter` abstraction — one `RenderResult`/`RenderPageResult` per page, 1-indexed `page_number`, fatal errors returned (never raised).
2. Implemented `PymupdfRendererAdapter` (PyMuPDF via `pymupdf`) rendering each page to PNG at a stable 150 DPI; detects encrypted/unopenable documents and per-page failures without aborting the whole document.
3. Added `DocumentService.store_rendered_pages()` which stores each rendered PNG in object storage under a deterministic, org/project/document/version-scoped key (`build_key` with a UUID5 `object_id`) and persists it on `DocumentPage.rendered_image_object_key` (column added in CP19 migration `0007`, nullable).
4. Integrated rendering into the worker's PARSE stage (`_do_parse`) — best-effort and non-fatal: a render/storage failure is recorded as a per-page `structural_metadata` warning and never fails parsing.
5. Made keys **idempotent**: re-rendering the same version/page/DPI overwrites the same storage key (no duplicate blobs); `store_pages` already deletes+recreates page rows on re-parse so image keys are always re-derived consistently.
6. Rendering is wired into `create_worker` (production) and is opt-in for tests via the `renderer=` argument; a `JobProcessor` constructed without a renderer skips rendering (safe default).

### How we verified it

- `PymupdfRendererAdapter` renders a real 3-page PDF to 3 ordered PNGs with valid PNG signatures (8 renderer unit tests).
- Encrypted/corrupt/unsupported-MIME PDFs produce `fatal_error`, never raise.
- `FakeRendererAdapter` produces deterministic, dependency-free PNGs.
- `DocumentService.store_rendered_pages` sets `rendered_image_object_key` per page, images are retrievable from storage, keys are idempotent across re-renders, fatal/per-page failures are annotated as warnings without images, and cross-tenant access is denied (7 service tests).
- Worker integration: a `JobProcessor` with a renderer persists image keys; without a renderer it is a no-op and never fails (2 worker tests).

### This checkpoint is complete only when

- [x] The system has a stable visual source even when text extraction is imperfect.
- [x] A `DocumentPage` row can be located and its rendered image retrieved from object storage.
- [x] Re-rendering a version does not duplicate stored image objects (deterministic keys).

### Implementation / PR note

- **Branch:** `cp20/rendered-page-assets`
- **`pyproject.toml`:** added `pymupdf>=1.25,<2.0`.
- **New package `tender_compliance_api/renderer/`:**
  - `adapter.py` — `RendererAdapter` ABC + frozen `RenderPageResult`/`RenderResult` dataclasses.
  - `pymupdf.py` — production renderer (`pymupdf`); 150 DPI PNG; safe on untrusted input (no JS/exec); per-page failure isolation; encryption → fatal.
  - `fake.py` — deterministic dependency-free PNG renderer for tests.
- **`document/service.py`:** added `store_rendered_pages()` (best-effort, tenant-scoped, deterministic UUID5 keys) + `_append_page_warning()` helper.
- **`tender_compliance_worker/processor.py`:** `JobProcessor` accepts `renderer: RendererAdapter | None`; `_do_parse` renders after `store_pages`; `_render_pages()` helper isolates failures.
- **`tender_compliance_worker/worker.py`:** `create_worker()` injects `PymupdfRendererAdapter`.
- **No new migration** — `rendered_image_object_key` already exists on `document_pages` (CP19 migration `0007`).
- **Tests:** 18 new tests in `tests/test_renderer.py`.
- **Verified:** `ruff check .` ✅, `mypy src/` ✅ (50 source files), `alembic upgrade head` ✅, `pytest` ✅ (169 tests = 151 prior + 18 new).

### Guardrail

- Rendered images are derived assets, not new source versions.

## ✅ Checkpoint 21 — Scanned-page detection and OCR

**Status:** DONE — PR #26

**Plain-English outcome:** Image-only/mixed pages are routed to OCR and OCR uncertainty is preserved.

### What we did

Page **detection** was already in place from CP19 (`pypdf` sets `ocr_needed=True` per page when native text is absent/untrustworthy; `DocumentPage.ocr_needed`/`ocr_confidence`/`extracted_text` and `DocumentVersion.ocr_name`/`ocr_version` columns exist). CP21 added the OCR **provider**:

1. New replaceable `ocr/` package mirroring `parser/`/`renderer/`:
   - `adapter.py`: `OcrAdapter` ABC + frozen `OcrResult`/`OcrWord` dataclasses (`text`, `confidence` `[0,100] | None`, optional per-word `bbox`). Confidence `None` = unknown, never "high".
   - `tesseract.py`: `TesseractOcrAdapter` (pytesseract + Pillow, 150 DPI render from CP20 images). Safe on untrusted input — no code execution. CPU-bound calls wrapped in `asyncio.to_thread`. Provider-availability errors (missing `tesseract` binary) propagate and are recorded per-page non-fatally; corrupt image → empty `OcrResult` (per-page, not raised).
   - `fake.py`: `FakeOcrAdapter` — deterministic test double returning configurable text/confidence/words (explicitly named "fake", never claims to be real OCR).
2. `DocumentService.apply_ocr()`: for each `ocr_needed` page, fetches its CP20 rendered image from object storage and runs the adapter. Persists `extracted_text` + `ocr_confidence`; clears `ocr_needed` only when **usable text** is produced (empty/zero-confidence OCR keeps the page flagged so the version is correctly `PARTIAL`). Provider name/version recorded on `DocumentVersion` only when the adapter was actually invoked. Missing rendered image / per-page OCR failure → warning, `ocr_needed` preserved — best-effort, non-fatal.
3. Worker PARSE job now runs the `OCR` stage (CP20 already rendered pages in the same job, so images are available): `JobProcessor` accepts `ocr: OcrAdapter | None`; `_do_ocr()` calls `apply_ocr` and always completes the OCR run (COMPLETED on success, FAILED only on a whole-stage exception); with no adapter the OCR stage is a no-op (zero regression). `create_worker` injects `TesseractOcrAdapter` (degrades to no-op if the binary is absent).
4. Removed the stale hard-coded `OCR_NAME`/`OCR_VERSION` defaults so provider identity is always sourced from the adapter that actually ran — never fabricated.
5. `pyproject.toml`: added `pytesseract>=0.3.10,<1.0` and `pillow>=10.0,<13.0`.

### How we verified it

- `tests/test_ocr.py` (16 real + 1 skipped-without-binary): FakeOcrAdapter deterministic text incl. `≥`, `≤`, `µ`, decimals, units, confusions; words/geometry; confidence `None` preserved; TesseractAdapter name/version + real-OCR smoke (skips when binary absent); `apply_ocr` scan-fill, native-skip (no provider recorded), missing-image (page kept flagged), OCR-exception (per-page warning, provider recorded), empty-text (page kept flagged), mixed doc, idempotent re-OCR (no overwrite), cross-tenant denial; worker scan→PARSED (4 COMPLETED runs, `ocr_name="fake"`, text filled, `ocr_needed=0`) and scan-without-adapter→PARTIAL (OCR no-op, `ocr_name=None` preserved).
- `ruff check .` ✅ · `mypy src/` ✅ (54 files) · `alembic upgrade head` ✅ · `pytest` ✅ (185 passed + 1 skipped; real-Tesseract test runs locally once the binary is installed).

### This checkpoint is complete only when

- [x] Each page has an inspectable native-text or OCR path and uncertainty metadata.
- [x] Image-only, digital, and mixed fixtures choose the expected path.
- [x] OCR uncertainty (confidence, empty/flagged pages) is preserved, not collapsed.

### Implementation / PR note

- **Branch:** `cp21/scanned-page-ocr`
- **New package `tender_compliance_api/ocr/`:** `adapter.py` (port + dataclasses), `tesseract.py` (TesseractOcrAdapter), `fake.py` (FakeOcrAdapter).
- **`document/service.py`:** added `apply_ocr()` (best-effort, tenant-scoped, per-page non-fatal).
- **`tender_compliance_worker/processor.py`:** `JobProcessor.__init__` accepts `ocr`; added `_do_ocr()`; routed `ProcessingStage.OCR` to it; removed stale `OCR_NAME`/`OCR_VERSION` constants and the unconditional `version.ocr_name`/`ocr_version` assignment (now sourced from the adapter).
- **`tender_compliance_worker/worker.py`:** `create_worker` injects `TesseractOcrAdapter` and passes it to `JobProcessor`.
- **`pyproject.toml`:** `pytesseract>=0.3.10,<1.0`, `pillow>=10.0,<13.0`.
- **No new migration** — `ocr_name`/`ocr_version`/`ocr_confidence`/`ocr_needed` columns already exist (CP19 migration `0007`).

### Guardrail

- Never silently correct meaning-bearing OCR. OCR uncertainty (confidence, no-text pages) is recorded as a review state, not silently treated as "recognized".

## ✅ Checkpoint 22 — DOCX adapter and format-appropriate provenance

**Status:** DONE — PR #27

**Plain-English outcome:** DOCX can enter the same pipeline without fake PDF metadata.

### What we did

1. `python-docx` adapter added under the existing `parser/` port, returning the
   same `ParseResult`/`PageResult` contract so DOCX documents flow through
   PARSE → OCR → EXTRACT unchanged.
2. DOCX is walked in body order (`w:p` and `w:tbl` children of
   `<w:body>`), so headings, paragraphs, lists, and table cells are
   preserved in source order as a single text segment per document.
3. Source locations: because `.docx` carries **no inherent page count**
   (page numbers are a renderer-side artifact), the document is surfaced as
   one `PageResult` (`page_number=1`, `page_count=1`) — *no fabricated
   page numbers*. A per-page warning makes the limitation explicit. This is
   the honest, format-appropriate provenance the guardrail requires.
4. Native `.docx` text is authoritative, so `ocr_needed=False` on the page
   (DOCX is never OCR'd in Phase 1; no rendered image is requested).
5. A new `CompositeParserAdapter` dispatches by MIME type, so a single
   `JobProcessor` accepts both PDF and DOCX. The processor was changed to
   record `version.parser_name`/`parser_version` from the **sub-adapter**
   (`parse_result.parser_name`), so a DOCX version records `"python-docx"`
   and a PDF `"pypdf"` — provenance is the real parser that ran, not a
   generic dispatcher label. On the unknown-MIME path the composite records
   its own identity and a fatal `ParseResult`.
6. `create_worker` now injects the composite (`application/pdf` →
   `PypdfParserAdapter`, `application/vnd...wordprocessingml.document` →
   `DocxParserAdapter`). DOCX-to-PDF preview/derivation deferred (not
   needed: DOCX has native text) — see CP23/CP36 for source rendering.

### How we verified it

- `tests/test_docx.py` (9 tests): `DocxParserAdapter` preserves heading +
  paragraphs + table cells in order; native text → `ocr_needed=False`; warns
  about no inherent page count; corrupt bytes → fatal `ParseResult` (never
  raised); unsupported MIME → fatal; empty DOCX → one empty page.
  `CompositeParserAdapter` dispatches PDF→pdf-adapter, DOCX→docx-adapter,
  records the sub-adapter identity on the `ParseResult`, and fatals on
  unknown MIME; `supported_mime_types` property. End-to-end worker test:
  a DOCX version reaches `PARSED` with `parser_name="python-docx"`, one
  `DocumentPage` (page 1, `ocr_needed=0`) carrying the extracted text and
  the provenance warning, and 4 COMPLETED stage runs.
- `ruff check .` ✅ · `mypy src/` ✅ (56 files) · `alembic upgrade head` ✅
  (no new migration — CP22 is logic only) · `pytest` ✅ (194 passed, 1
  skipped real-Tesseract) · `apps/web` `npx tsc --noEmit` ✅ (unchanged).

### This checkpoint is complete only when

- [x] DOCX can use the downstream requirement pipeline with trustworthy source references.
- [x] No fabricated page number is created when unavailable.
- [x] DOCX fixtures preserve paragraphs and tables (in source order).

### Implementation / PR note

- **Branch:** `cp22/docx-adapter`
- **New:** `tender_compliance_api/parser/docx.py` (`DocxParserAdapter`).
- **New:** `tender_compliance_api/parser/composite.py` (`CompositeParserAdapter`).
- **`tender_compliance_api/parser/__init__.py`:** export both adapters.
- **`tender_compliance_worker/processor.py`:** record
  `version.parser_name`/`parser_version` from `parse_result` inside
  `_do_parse` (covers success + fatal-parse paths); removed the
  post-stage composite-name assignment so the real sub-parser identity is
  preserved. Storage-missing path intentionally leaves parser identity NULL
  (parse never ran).
- **`tender_compliance_worker/worker.py`:** `create_worker` default parser is
  the composite (PDF + DOCX).
- **`pyproject.toml`:** added `python-docx>=1.2,<2.0`.
- **No new migration** — parses into the existing `DocumentPage` table.

### Bynd reuse notes

- **Reference:** `Bynd-ai/table_grid` uses Docling for high-fidelity PDF/DOCX
  structural conversion.
- Decision for Phase 1: adopted `python-docx` (pure-Python, no native build)
  rather than Docling. Docling remains the candidate for higher-fidelity
  heading/list/table + page-boundary reconstruction; a CP22-range benchmark
  on tender fixtures (heading/list/table preservation, source-location
  fidelity, runtime, memory, failure behaviour) will decide whether to
  switch before CP23/CP36. Until then the single-segment DOCX representation
  is honest (no fabricated pages).

### Guardrail

- Do not pretend converted page numbers are original-source pages unless that representation is explicitly defined.

## ✅ Checkpoint 23 — DocumentPage persistence and structural cleanup

**Status:** DONE — PR #28

**Plain-English outcome:** Page-level source text/assets/metadata survive processing and can support extraction/citations.

### What we did

The `DocumentPage` table and its unique `(document_version_id, page_number)`
identity, `ix_document_pages_version` lookup index, and the raw
`extracted_text` column already existed from CP19. CP23 added the two signals
that make persisted pages safe to clean *without* losing provenance:

1. **Header/footer dedup** (`parser/cleanup.py`, pure function
   `cleanup_pages`): deterministically detects lines that are the first/last
   non-empty line of a page and recur textually-identically on `>= max(2,
   ceil(50%))` of the version's pages (and are short, non-clause-numbered).
   Recurrence is required, so unique body text, varying per-page lines
   (e.g. `"Page 3"`), numbered-clause references (`1.2.3`), and long lines are
   never stripped. The input `PageResult` objects are not mutated.
2. **Raw-vs-cleaned separation**: new nullable `cleaned_text` column on
   `document_pages` (migration `0008_document_page_cleaned_text`) holds the
   page text with detected header/footer noise removed. `extracted_text`
   stays the immutable authoritative source — cleanup never destroys it.
3. **Structure in `structural_metadata`**: `store_pages` now also records
   `headers`/`footers`/cleanup-`warnings` (merged with parser warnings) so
   downstream can load per-page structure from durable storage and see
   exactly what was stripped.

### How we verified it

- `tests/test_cleanup.py` (10 tests): pure `cleanup_pages` strips repeated
  headers/footers, leaves unique body text / varying lines / clause numbers /
  long lines untouched, never mutates input, single-page not stripped; plus
  `store_pages` integration: `cleaned_text` populated and raw text preserved,
  `structural_metadata` records `headers` + warning, and reprocessing
  replaces (does not duplicate) page rows.
- `tests/test_migration.py`: updated expected head revision to
  `0008_document_page_cleaned_text` (new migration).
- `ruff check .` ✅ · `mypy src/` ✅ (57 files) · `alembic upgrade head` ✅
  (`0001_initial_baseline → 0008_document_page_cleaned_text`) · `pytest` ✅
  (204 passed, 1 skipped real-Tesseract) · `apps/web npx tsc --noEmit` ✅.

### This checkpoint is complete only when

- [x] Page-level source text/assets/metadata survive processing and can support extraction/citations.
- [x] Reprocessing does not duplicate page rows (`store_pages` deletes-then-inserts; tested).
- [x] Cleanup removes repeated noise without deleting real requirement text (`cleaned_text` is derived; `extracted_text` is immutable; tested).

### Implementation / PR note

- **Branch:** `cp23/page-cleanup`
- **New:** `tender_compliance_api/parser/cleanup.py` (`cleanup_pages`, `PageCleanup`).
- **`db/models.py`:** `DocumentPage.cleaned_text` column + docstring.
- **`document/service.py`:** `store_pages` computes `cleanup_pages(parse_result.pages)` and persists `cleaned_text` + `headers`/`footers`/`warnings` into `structural_metadata`; raw `extracted_text` unchanged.
- **`parser/__init__.py`:** export `PageCleanup`, `cleanup_pages`.
- **`alembic/versions/0008_document_page_cleaned_text.py`:** add nullable `cleaned_text` column (drop in downgrade).
- **No behavioral change** to PDF/DOCX parsing or OCR; the OCR stage still fills `extracted_text`/`ocr_confidence` for `ocr_needed` pages (CP21) independently of the raw/cleaned split.

### Bynd reuse notes

- **References:** `table_grid`, `ocr-table-fixes-discovery`, and Bynd table/OCR experiments.
- Decision for Phase 1: deferred optional cell-level table structure (row/column position, cell confidence, bbox) — full clause/numbering hierarchy and cell-level metadata belong to CP25–CP27 (chunking/chunk windows). CP23 keeps the raw-vs-cleaned split and header/footer provenance so that later normalization can always be audited from `extracted_text` + `structural_metadata`.
- Structured table metadata supplements raw source text; it never replaces it.

### Guardrail

- Do not perform semantic rewriting in cleanup. (Honoured: only identical,
  repeated, non-clause, length-capped positional lines are removed, and only
  into the derived `cleaned_text`; the raw `extracted_text` is never
  modified.)

## ✅ Checkpoint 24 — Processing retry, idempotency, and partial failure

**Status:** DONE — PR #29 merged.

**Plain-English outcome:** Reprocessing a document is safe and incomplete work remains visible.

### What we will do

1. Give each processing run an ID.
2. Use deterministic page reconciliation/upserts.
3. Bound provider/network retries.
4. Separate retryable/permanent errors.
5. Represent partial page success.
6. Add retry API/action for eligible failures.
7. Do not destroy prior immutable source bytes during reprocessing.

### How we will verify it

- Run the same document twice without duplicate pages.
- Single-page failure stays visible instead of disappearing inside success.

### This checkpoint is complete only when

- Operators can explain what retry will do and why it is safe.

**Completion summary (PR #29):**

- The version-level state machine, deterministic `run_id` (`make_job_id(version_id, stage)`), idempotent `store_pages` (delete-then-recreate), and `FAILED/PARTIAL → QUEUED` transitions already existed on `main` (CP17/CP21/CP23).
- CP24 closes the remaining gaps:
  - **`DocumentService.requeue_version`** — transitions `FAILED`/`PARTIAL → QUEUED` (rejects terminal `PARSED` with `TransitionError`), returns the deterministic PARSE `run_id`, is idempotent for already-queued versions, tenant-isolated, and audit-logged (`document.retry`). Source bytes (`StoredObject`, `restricted`) are never mutated or destroyed.
  - **`POST /projects/{project_id}/documents/{document_id}/versions/{version_number}/retry`** — thin route delegating to `requeue_version` + deterministic queue `enqueue`; returns 200/`run_id`, 404 for missing/wrong-project, 409 for terminal `PARSED`.
  - **Per-page error visibility** — `store_pages` now persists `PageResult.error` into `structural_metadata["error"]` so a single failed page never silently disappears inside an otherwise-successful parse.
- **Tests:** `TestRetryVersion` (service: failed/partial→queued, parsed rejected, idempotent, cross-tenant denied) + `TestRetryProcessingApi` (HTTP: 200/409/404/404-idempotent; asserts deterministic `run_id`, single enqueued job) + `TestStorePagesCleanup.test_store_pages_persists_page_error`.
- **Verification:** `pytest` 215 passed / 1 skipped (real-Tesseract skip), `ruff check .` clean, `mypy src/` clean, `alembic upgrade head` applies `0001→0008`, `apps/web npx tsc --noEmit` clean. No new migration (JSON metadata + service-only).
- **Known limitations:** operator retry re-runs the full PARSE→OCR→CLEANUP→EXTRACT pipeline; the `attempt` counter in the Worker retry loop is reset to 1 on operator retry (a fresh worker attempt), while `ProcessingRun.attempt` is the per-version-per-stage max+1 (auditable).

### Bynd reuse notes

- **Reference:** `Bynd-ai/validation-engine` source cache.
- Cache authoritative extraction by **document content hash + physical page/segment + parser/extractor version**, never URL or filename alone.
- Version the cache schema, verify cached coverage for requested pages, and invalidate on content/version mismatch.
- Cache source material/derived extraction for speed; never treat cached semantic verdicts/compliance decisions as source truth.
- Persist long-running stage artifacts/checkpoints incrementally where that makes retry/debugging safer.

### Guardrail

- Retry is not a new source version.

# Stage E — Conservative technical requirement extraction and provenance

Extract explicit obligations only, validate every model response, and persist source-backed requirements.

## ✅ Checkpoint 25 — Structured extraction schema and trusted source-window contract

**Status:** DONE — PR #30 merged.

**Plain-English outcome:** The LLM can only propose candidates in a strict schema tied to trusted source metadata.

### What we will do

1. Create Pydantic candidate schemas.
2. Require raw source fragment, proposed normalized text, uncertainty flags, parent/group hints, and observed clause/section when available.
3. Carry trusted version/page/window metadata outside model control.
4. Use nullable/tri-state mandatory values.
5. Reject malformed enums/structures.
6. Prevent model-provided page data from overriding trusted source context.

### How we will verify it

- Schema tests reject missing sources, invalid states, and malformed values.
- A model cannot move a candidate to a different page.

### This checkpoint is complete only when

- There is a machine-enforced boundary between model suggestion and persistable requirement.

**Completion summary (PR #30):**

- Added `tender_compliance_api/extraction/` package with the Phase 1 extraction schema:
  - `RequirementCandidate` — the model-owned output. Carries **no** trusted
    location fields (`page_number`/`version_id`/`bbox`/etc. are absent and
    `extra="forbid"`), so the model cannot attach or move a page.
  - `TrustedSourceContext` — service-owned source window (org/doc/version/page,
    clause, char offsets, bbox, ocr_confidence, location_type, `source_text`),
    built via `from_page(DocumentPage, …)`.
  - `SourcedRequirementCandidate` — the boundary object: required `source`
    + `:meth:validate_source` (citation must be a whitespace-normalized
    substring of the trusted window) + `:meth:is_persistable` (CONFIRMED +
    citation verified). A bare candidate is not persistable.
  - Enums: `RequirementType` (obligation/prohibition/permission),
    `UncertaintyLevel` (confirmed/uncertain/abstain — tri-state mandatory),
    `LocationType` (exact/approximate). `CandidateValidationError` typed error.
- **Boundary guarantees:** missing/malformed enum/structure → construction
  `ValidationError` (`extra="forbid"`, strict enums, required fields); a
  citation not present in the trusted window → `CandidateValidationError`
  (model cannot move a candidate to a different page).
- Tests: `tests/test_extraction.py` (20 tests) — candidate schema, trusted
  context (incl. `from_page` from a parsed `DocumentPage`), and the sourced
  boundary (persistable gate, missing source, malformed/unknown enums,
  no-page-on-candidate, different-page rejection, whitespace tolerance,
  uncertain/abstain not persistable).
- **Verification:** `pytest` 235 passed / 1 skipped (real-Tesseract skip),
  `ruff check .` clean, `mypy src/` clean (59 files), `alembic upgrade head`
  applies `0001→0008` (no new migration), `apps/web npx tsc --noEmit` clean.
- **Known limitations / deferred:** no DB table for candidates yet (CP30
  persists `Requirement`); the LLM adapter that produces candidates is CP26;
  multi-page windows + fuzzy citation matching live in CP27/CP31. CP25
  delivers only the schema + boundary, intentionally leaving the model call
  to CP26.

### Guardrail

- Never persist free-form model prose as a valid requirement.

## ✅ Checkpoint 26 — LLM extraction adapter, prompt versions, and run metadata

**Status:** DONE — PR #31 merged.

**Plain-English outcome:** Model calls are controlled, provider-agnostic, and auditable.

### What we will do

1. Define a structured-extraction adapter.
2. Keep system instructions separate from untrusted document text.
3. Use structured output/schema enforcement where supported.
4. Record provider, model, prompt version, schema version, run ID.
5. Add timeouts and bounded retries.
6. Minimize source payloads to relevant windows.
7. Support a deterministic fake provider for tests.

### How we will verify it

- Test adapter drives extraction without network calls.
- Stored run metadata identifies the exact extraction configuration.

### This checkpoint is complete only when

- Changing providers does not require rewriting document services.

### Bynd reuse notes

- **References:** `engineering-docs/llm-cost-logging-sop.md` and `validation-service` provider telemetry.
- Every LLM call must log its processing `run_id`, call site, model, provider-reported input/output/cache tokens when available, elapsed time, and best-effort cost.
- Unknown model pricing is null/unknown, never zero. Do not fabricate token counts.
- Emit one run summary even when the run fails.

### Guardrail

- Document text can never invoke tools or override application instructions.

**Completion summary (PR #31):**

- Added the provider-agnostic `:class:LlmAdapter` port with frozen
  `LlmCallConfig` / `LlmCallResult` / `ExtractResult` / `LlmCallError` (CP26):
  providers drop in by subclass, never by rewriting services.
- `FakeLlmAdapter` — deterministic, no-network adapter (serves pre-canned
  `ExtractionResponse`s, records an audited `LlmCallResult` per call).
- `OpenAiLlmAdapter` — production default (`gpt-4o`, structured output parsed
  into `ExtractionResponse`). The `openai` package is imported lazily so
  `create_worker` and the worker/test suite never require it; a real call
  requires `OPENAI_API_KEY` and is opt-in only (`CP26_OPENAI_REAL_CALL=1`).
- `extraction_runs` audit table (migration `0009`) + `ExtractionRun` /
  `ExtractionRunStatus` models.  Each LLM call is anchored to its EXTRACT-stage
  `ProcessingRun` and records provider/model/prompt+schema version, latency,
  provider-reported tokens, finish reason, and best-effort cost.  Token counts
  and cost are nullable — `NULL` means "unknown", never a fabricated zero (per
  the LLM cost-logging SOP in the checkpoint Bynd notes).
- `DocumentService.log_llm_call` persists the audit record (flush, no source
  mutation).
- `create_worker` injects a default `OpenAiLlmAdapter`; `JobProcessor` accepts
  an injectable `llm`.  The EXTRACT stage still no-ops (CP28 calls the adapter).
- Real-OCR/test-call skips: `openai` not in `pyproject` deps (lazy import);
  the live-call test skips without `CP26_OPENAI_REAL_CALL` so CI never incurs
  cost.
- Tests: `tests/test_extraction_pipeline.py` (10 passed, 1 opt-in skip) +
  updated `tests/test_migration.py` (head = `0009_extraction_runs`).  Gate:
  pytest 245 passed/2 skipped, ruff clean, mypy 63 files clean, `alembic
  upgrade head` 0001→0009, web `tsc --noEmit` clean.

## ✅ Checkpoint 27 — Chunking, overlap, clause hierarchy, tables, and multi-page windows

**Status:** DONE — PR #32 merged.

**Plain-English outcome:** Extraction sees enough context to understand complicated tender structure without losing provenance.

### What we will do

1. Chunk by trusted page/section/clause/table boundaries before token count.
2. Use bounded overlap for cross-boundary requirements.
3. Carry stable chunk IDs and trusted metadata.
4. Preserve nested bullet hierarchy and parent-child context.
5. Preserve table row/column headers.
6. Allow multiple source fragments for multi-page requirements.
7. Keep overlap small enough that duplicates are manageable.

### How we will verify it

- Fixtures cover boundary-spanning requirements, nested bullets, tables, and multi-page clauses.

### This checkpoint is complete only when

- A requirement can span source fragments without being detached from each location.

### Bynd reuse notes

- **References:** `validation-engine/pdf/page_authority.py` and `pdf/windows.py`.
- Pass trusted source authority (document version/page/window) into chunking instead of letting deep matching/model code choose source pages.
- For cross-page windows, use conservative deterministic continuation signals and retain every contributing page.
- URL fragments/search strings are navigation hints, never provenance authority.

### Guardrail

- Do not flatten structure in a way that changes table or clause meaning.

**Completion summary (PR #32):**

- Added `extraction/chunking.py` with a **pure, deterministic** chunker
  (`build_source_windows`) producing `SourceWindow` fragments from a version's
  `DocumentPage` rows.  No DB schema change (CP27 is in-memory windowing).
- Boundaries are structural, never flattening: **page** (trusted
  `page_number`), **clause/section** headers (same numbered-clause convention
  as `parser.cleanup`), and **tables** (consecutive ``|``-rows kept together,
  header row preserved as `table_context`).  Windows break only *between*
  segments; a blank line flushes a segment and an oversized atomic segment is
  emitted whole (no mid-table / mid-clause splits → no data loss).
- **Stable `chunk_id`s**: content-addressed to version + page span + char
  span + clause + content hash, so the same input yields identical windows
  across re-runs.
- **Bounded overlap**: each window after the first carries `overlap` = the
  previous window's tail (`overlap_chars`, validated `< max_chars`); recorded
  (not silently merged) so CP29 can reconcile.
- **Honest multi-page provenance**: a window spanning pages carries one
  `TrustedSourceContext` per contributing page, each with **exact** char
  offsets within that page's `cleaned_text`, `location_type=EXACT`, and the
  shared trusted window text as `source_text`.  `source_pages` are the real
  input pages — no synthetic page numbers or version ids (AGENTS "never
  fabricate").
- `SourceWindow` / `build_source_windows` re-exported from `extraction`.
- Tests: `tests/test_chunking.py` (13 cases) covering boundary-spanning splits,
  table atomicity + header preservation, nested-clause hierarchy, multi-page
  windows retaining every page, deterministic chunk IDs, no-fabrication, and
  overflow-safety.
- Gate: pytest 258 passed/2 skipped, ruff clean, mypy 64 files clean, `alembic
  upgrade head` unchanged (head `0009_extraction_runs`), web `tsc --noEmit`
  clean.

## ✅ ~~Checkpoint 28 — Requirement candidate extraction, splitting, grouping, and abstention~~

**Status:** DONE — PR #33 merged.

**Plain-English outcome:** Explicit technical obligations become reviewable candidate rows without invented meaning.

### What we will do

1. Extract explicit requirements only.
2. Preserve all numbers, units, conditions, scope, and modal language.
3. Split independent obligations.
4. Keep coupled conditions together when split would change meaning.
5. Support parent/child relationships.
6. Allow abstention on ambiguous/non-requirement text.
7. Flag OCR/structure uncertainty.
8. Validate output before reconciliation.

### How we will verify it

- Benchmark covers one sentence→many requirements and many sentences→one requirement.
- Invented requirement rate is measured.

### This checkpoint is complete only when

- Every candidate has supporting source text and safe structure for review.

### Guardrail

- Do not optimize recall by inferring requirements that are not stated.

### Completion summary (PR #33)

**Why:** The EXTRACT stage previously no-opped (`JobProcessor.__init__(llm=None)` →
stage completed as empty). Without calling the LLM, there were no candidates to
review (CP29) or refine into requirements (CP30), so the pipeline produced
nothing after parsing/cleanup. CP28 makes the EXTRACT stage actually run the
extraction adapter on the CP27 source windows.

**What changed:**
- `extraction/extractor.py` (new): `extract_from_windows(windows, llm, *, log_call, prompt_version, schema_version) -> ExtractionOutcome`. For each CP27 `SourceWindow` it builds the user payload (`overlap` + text), calls `LlmAdapter.extract` (the EXTRACTION_SYSTEM_PROMPT is the system message; document text only enters the user message), audits every call via the `log_call` callback (CP26), and converts each `RequirementCandidate` into a `CandidateRecord` anchored to the window's primary `TrustedSourceContext` via `SourcedRequirementCandidate.validate_source` (CP25 citation-substring boundary). OCR/structure-uncertain windows (`SourceWindow.ocr_warning`, computed end-to-end in CP27's chunker from `page.ocr_needed` and `structural_metadata["error"]`) elevate `CONFIRMED`→`UNCERTAIN`. ABSTAIN candidates are kept (audit, non-persistable). Per-window `LlmCallError` is logged and skipped so a transient provider outage does not strand the version.
- `db/models.py`: `ExtractionCandidate` table (one row per candidate, tenant-scoped via `document_version_id`, FK to `processing_runs`, `sources_json` carrying every contributing source fragment, `ocr_warning`/`is_valid`/`persistable` flags, verbatim `raw_source`/`normalized_text`). No Phase-2/vendor-compliance columns.
- `alembic/versions/0010_extraction_candidates.py`: migration (head advances to `0010_extraction_candidates`).
- `document/service.py`: `get_run` (tenant-scoped EXTRACT-run lookup) and `store_extraction_candidates` (persist `CandidateRecord`s; only `persistable=True` rows can be promoted later by CP30).
- `worker/processor.py`: `STAGES` EXTRACT dispatch now calls `_do_extract` (was a no-op `else`); `_do_extract` loads pages, builds windows (CP27), runs the orchestrator, logs calls, persists candidates, and completes the run. When `llm is None` it still completes as a clean no-op, preserving the existing `test_worker.py` contract.
- `extraction/adapter.py` / `fake.py` / `openai_adapter.py`: the previously-uncommitted in-flight `provider`/`model` port properties (abstract on `LlmAdapter`; concrete on `FakeLlmAdapter`/`OpenAiLlmAdapter`) are finalized here, since CP28's orchestrator reads `llm.provider`/`llm.model` for audit provenance.
- `extraction/__init__.py`: re-exports `CandidateRecord`, `ExtractionOutcome`, `extract_from_windows`.

**Scope:** EXTRACT-stage candidate extraction only. Does **not** implement CP29 (duplicate/reconciliation), CP30 (refined `Requirement` refinement), or any Phase-2/vendor-compliance behavior.

**Evidence/provenance impact:** Every persisted candidate carries its `chunk_id`, the window's trusted `sources_json` (document_id/version_id/page_number/clause_number/source_text/char offsets), verbatim `raw_source`, and `ocr_warning`. Candidates whose `raw_source` is not a substring of the trusted window are recorded `is_valid=False` with a `rejection_reason` (never presented as a requirement). EXTRACT runs are no longer empty — `extraction_runs` audit rows now have provider/model/prompt_version/schema_version.

**Verification:**
- `tests/test_extraction_extractor.py` (new, 12 cases): happy-path validation+persistability, fabrication rejection, OCR-uncertainty elevation (CONFIRMED→UNCERTAIN), structural-error elevation via the real chunker, ABSTAIN kept-but-not-persisted, multi-window one-call-per-window, empty no-op, LLM-failure audit+skip, overlap in payload, JSON-serializable `sources_json` (uuids as strings), provider/model/call_site echo. Pure-logic (FakeLlmAdapter), no network.
- `tests/test_extraction_pipeline.py` (CP26 file, +3 cases): end-to-end orchestrator→`log_llm_call`→`store_extraction_candidates`→DB read-back (valid+persistable, OCR-elevated, fabrication rejection, empty→0 rows).
- `tests/test_migration.py`: head bumped to `0010_extraction_candidates` + `extraction_candidates` table added to `_APP_TABLES`.

**Risks / limitations:**
- Per-window LLM failures are logged and skipped (best-effort) rather than retried within the stage; retry semantics are deferred to CP31. A version where *all* windows fail yields zero candidates but still completes the EXTRACT run (no stranded version).
- `sources_json` is stored as a JSON dump (portable, indexable only by `chunk_id`/`document_version_id`/`processing_run_id`); richer source-location querying is deferred to CP30/CP35.

**Gate (run from `apps/api`):** `pytest` 273 passed / 2 skipped; `ruff check .` All checks passed; `mypy src/` Success (65 files); `alembic upgrade head` → `0010_extraction_candidates`; `npx tsc --noEmit` (apps/web) clean.

## ✅ ~~Checkpoint 29 — Duplicate/header/footer/overlap reconciliation~~

**Status:** DONE — PR #34 merged.

**Plain-English outcome:** Repeated source windows do not flood the matrix with duplicate rows.

### What we will do

1. Use deterministic source fingerprints before fuzzy/semantic similarity.
2. Compare overlapping source spans.
3. Remove chunk-overlap duplicates predictably.
4. Keep repeated but materially distinct obligations.
5. Record reconciliation decisions.
6. Prefer a possible duplicate for review over silently deleting a distinct requirement.

### How we will verify it

- Overlap duplicates collapse.
- Repeated headers/footers never become requirements.

### This checkpoint is complete only when

- Duplicate rate is controlled without aggressive semantic merging.

### Guardrail

- Similar wording alone is not proof two requirements are the same.

### Completion summary (PR #34)

**Why:** With CP28 emitting one candidate per window, a requirement that spans a
chunk boundary (or a document header/footer re-emitted as a "requirement" across
pages) produces duplicate candidate rows. This would inflate the compliance
matrix and corrupt any downstream count. CP29 deduplicates these
deterministically **without aggressive semantic merging** — the AGENTS guardrail
("similar wording alone is not proof two requirements are the same") is
respected by deduping only on whitespace-normalized text + shared/overlapping
source pages, and by **flagging** rather than silently deleting identical-text
on distinct pages.

**What changed:**
- `extraction/reconcile.py` (new): pure `reconcile(candidates -> ReconciliationResult)`.
  Buckets candidates by whitespace-normalized `normalized_text` (deterministic
  `sha256[:16]` group id). Per fingerprint bucket:
    - **one member** → `singleton` (kept).
    - **multiple members sharing ≥1 source page** → `dedup_exact` (keep first in
      stable `(chunk_id, candidate_id)` order; the rest are `deduped=True` — audit-only,
      not promotable). Catches chunk-overlap duplicates and verbatim re-emission.
    - **multiple members on disjoint pages** → `flagged_review` (keep ALL, none
      deleted) — header/footer bleed flagged for human review, never silently merged.
  Idempotent and order-independent (stable sort first).
- `db/models.py`: `ExtractionCandidate.reconciliation_group_id`/`deduped`/
  `reconciliation_decision` columns + new `ExtractionReconciliation` audit table
  (one row per pass, `summary` JSON of counts). Tenant-scoped via
  `document_version_id` FK (CASCADE). Phase 1 only — no vendor-compliance columns.
- `alembic/versions/0011_extraction_reconciliation.py`: `ALTER extraction_candidates`
  (add 3 columns + index) + `CREATE extraction_reconciliations`. Head → `0011`.
- `document/service.py`: `reconcile_version_candidates(auth, document_id, version_number, *, run_id)` —
  loads persistable+source-validated candidates (tenant-scoped), runs `reconcile`,
  bulk-updates each candidate's reconciliation columns, writes one audit row.
  Re-runnable (idempotent).
- `worker/processor.py`: `_do_extract` now calls `reconcile_version_candidates`
  after `store_extraction_candidates` (best-effort — never strands the version).
- `extraction/__init__.py`: re-exports reconcile symbols.

**Scope:** Deduplication reconciliation only. Does **not** promote candidates to
refined `Requirement` objects (CP30), nor perform fuzzy/semantic dedup, nor any
Phase-2/vendor work.

**Evidence / provenance impact:** Every persisted candidate now carries a stable
`reconciliation_group_id` and a `reconciliation_decision`. Deduped duplicates keep
their source provenance (`sources_json`) and remain queryable for the invented-requirement
and duplicate rate audits; flagged-review groups stay promotable and grouped for CP35
human review. A single `extraction_reconciliations` audit row records the pass
(provider/run/time implicit via FK + summary counts).

**Verification:**
- `tests/test_extraction_reconcile.py` (new, 11 pure-logic cases): empty,
  singleton, overlap-dedup (same page + partial-page overlap), identical-text-
  distinct-pages flagged-not-deleted, mixed document (dedup+singleton+flagged),
  determinism under reordering, content-addressed group id, whitespace
  fingerprinting, no-source-fragment flagging, and distinct-requirements-same-page
  kept as separate singletons.
- `tests/test_extraction_pipeline.py` (+3 cases): end-to-end
  `store_extraction_candidates` → `reconcile_version_candidates` → DB read-back
  (deduped=True on duplicate, shared group_id, audit row summary; flagged-review
  keeps both rows, shared group_id; idempotent double-run yields identical columns).
- `tests/test_migration.py`: head bumped to `0011_extraction_reconciliation`;
  `extraction_reconciliations` added to `_APP_TABLES`.

**Risks / limitations:**
- Dedup is text+source-page based only (no semantic similarity). Two materially
  distinct obligations that happen to share verbatim wording on the same page are
  treated as duplicates (first kept) — this is the intended conservative behavior
  for overlap duplicates; truly distinct same-text requirements should live on
  distinct pages (→ `flagged_review`) or differ in clause/scope (out of CP29 scope;
  CP30/CP34 normalize scope).
- Reconciliation runs once per EXTRACT pass; CP31 will add explicit retry/re-run
  semantics and a reconciliation history.

**Gate (run from `apps/api`):** `pytest` 287 passed / 2 skipped; `ruff check .` All
checks passed; `mypy src/` Success (66 files); `alembic upgrade head` →
`0011_extraction_reconciliation`; `npx tsc --noEmit` (apps/web) clean.

## ✅ ~~Checkpoint 30 — Exact/approximate source anchors and Requirement persistence~~

**Status:** DONE — PR #35 merged.

**Plain-English outcome:** Only validated requirements are stored, each with the strongest source location actually known.

### What we will do

1. Add `Requirement` and `RequirementSource`.
2. Resolve exact source text back to stored page text deterministically where possible.
3. Store offsets and bounding boxes when reliable.
4. Mark location precision EXACT/APPROXIMATE.
5. Keep clause/section nullable when unknown.
6. Persist multiple source fragments when needed.
7. Transactionally persist validated candidates.
8. Quarantine/record invalid model output.
9. Design reprocessing so human-reviewed rows are never silently overwritten.

### How we will verify it

- Exact anchors round-trip to expected source text.
- Approximate anchors stay labeled.
- Reprocessing does not duplicate unchanged rows.

### This checkpoint is complete only when

- Every normal persisted requirement has trustworthy provenance and stable identity.

### Bynd reuse notes

- **References:** `validation-engine`, `industry-report-agentic`, and Bynd citation viewers.
- Source authority comes from immutable document/page records, never a citation URL fragment or an LLM-provided page number.
- Search/fuzzy text may help locate a span **inside an already-authorized page**, but may not silently broaden source scope.
- Preserve EXACT vs APPROXIMATE as a first-class property; never upgrade precision just because a plausible fuzzy match exists.

### Guardrail

- Never fabricate missing coordinates/page/clause metadata.

### Completion summary (PR #35)

**Why:** CP28/CP29 emit validated, deduped, source-anchored candidates but keep
them in transient `extraction_candidates` rows. There was no persisted,
human-reviewable `Requirement` object with a stable identity and a strong
source location. CP30 promotes the surviving candidates into
`:class:`~tender_compliance_api.db.models.Requirement`` rows with EXACT/APPROXIMATE
source anchors and a content-addressed `promotion_key` so reprocessing never
silently duplicates a row or overwrites a human-reviewed state.

**What changed:**
- `db/models.py`: `Requirement` (tenant-scoped via `document_version_id`, FK to
  `processing_runs`, `promotion_key`, `reconciliation_group_id`, verbatim
  `normalized_text`/`raw_source`, `requirement_type`/`uncertainty`/`clause_number`/
  `ocr_warning`, Phase-1 `review_state` enum `UNREVIEWED/REVIEWED/
  NEEDS_CLARIFICATION/OCR_WARNING` defaulting `unreviewed`) and `RequirementSource`
  (one row per contributing page fragment: `page_number`, `clause_number`,
  `char_start`/`char_end`, `bbox`, `ocr_confidence`, `location_type`
  exact/approximate, verbatim `source_text`). No Phase-2/vendor-compliance
  columns. `RequirementReviewState` StrEnum defined alongside the other enums.
- `alembic/versions/0012_requirements.py` (new): `CREATE TABLE requirements`
  (incl. `uq_requirements_version_promotion_key`), `CREATE TABLE
  requirement_sources`, indexes; `review_state`/`location_type` stored as VARCHAR
  (SQLite-compatible, mirroring CP26 `0009`'s `status` column); the ORM
  `Enum(..., name=...)` maps the Python enum. Head → `0012_requirements`.
- `extraction/requirement.py` (new): pure promotion/anchor logic:
  `promotion_key(normalized_text, requirement_type, clause_number, page_numbers)`
  (`sha256[:16]` of whitespace-normalized text + type + clause + sorted-unique
  pages); `to_promotion_input(row)` projects a candidate (reads page numbers from
  the trusted `sources_json`, never fabricating them); `resolve_sources(raw_source,
  sources_json)` returns EXACT (`raw_source` is a literal substring of the page
  `source_text` → real `char_start`/`char_end`) or APPROXIMATE (reuses the fragment's
  stored span, no fabricated offsets). `ResolvedSource`/`PromotionInput` frozen
  dataclasses.
- `document/service.py`: `persist_requirements(auth, document_id, version_number, *,
  run_id=None) -> (inserted, skipped)` — selects candidates where
  `is_valid AND persistable AND deduped=False`, skips any whose `promotion_key`
  already exists (preserving that row's existing `review_state`), else inserts the
  `Requirement` + its `RequirementSource` anchors (flush per requirement).
- `worker/processor.py`: `_do_extract` calls `persist_requirements` after
  `reconcile_version_candidates` (best-effort, logs on failure, never strands the
  version); `JobProcessor(llm=None)` keeps EXTRACT a clean no-op (preserves
  `test_worker.py`).
- `extraction/__init__.py`: re-exports `promotion_key`, `resolve_sources`,
  `to_promotion_input`, `PromotionInput`, `ResolvedSource`.

**Scope:** Candidate → persisted `Requirement` promotion only. Does **not**
implement human review/edit (CP35-CP40), matrix projection or export (CP41-CP42),
normalization of numeric/unit constraints (CP32-CP34), or any Phase-2/vendor work.

**Evidence/provenance impact:** Every persisted requirement is traceable to
`document_version_id` → `RequirementSource.page_number`/`clause_number`/
`char_start`/`char_end`/`bbox`/`ocr_confidence`/`location_type`/`source_text`,
with `raw_source` preserved verbatim (never mutated). EXACT is only used when the
candidate's `raw_source` is a literal substring of the trusted page text;
otherwise APPROXIMATE is labeled and no offset is fabricated. OCR-derived
candidates are UNCERTAIN (non-persistable since CP28) — promoted requirements carry
`ocr_warning=False` at promotion time; `OCR_WARNING` review state is reserved for
CP35 human review — honoring the AGENTS rule that missing evidence is not the same
as contradictory evidence.

**Verification:**
- `tests/test_extraction_promotion.py` (new, 8 pure cases): `promotion_key`
  determinism/changes-by-text/page/clause/type and 16-hex shape; `to_promotion_input`
  page extraction (order preserved, missing sources → empty) and promotion-key
  derivation; `resolve_sources` EXACT literal-substring offsets, bbox/ocr passthrough,
  whitespace-difference → APPROXIMATE fallback (no fabricated offset), no-source-text →
  APPROXIMATE, multi-fragment independent resolution, fragment without page_number skipped.
- `tests/test_extraction_pipeline.py` (+4 `TestPromotionPersistence` cases):
  exactly-anchored requirement read back with `review_state=UNREVIEWED` + correct
  EXACT `char_start`/`char_end`; reprocess idempotency (0 inserted, 1 skipped,
  human-set `REVIEWED` state preserved, single row); deduped candidates not promoted;
  non-literal raw_source round-trips as APPROXIMATE with the fragment's stored span;
  `promotion_key` matches the content-addressed formula.
- `tests/test_migration.py`: head bumped to `0012_requirements`; `requirements` and
  `requirement_sources` added to `_APP_TABLES`.

**Risks / limitations:**
- `promotion_key` is text/type/clause/pages only; genuinely reworded obligations
  on the same pages get a new key (fresh row). This is intended — rewording may
  change meaning and must be re-reviewed.
- APPROXIMATE anchors reuse the fragment's `char_start`/`char_end` as recorded by the
  chunker; if that span was itself approximate, the requirement is flagged
  APPROXIMATE (never silently upgraded to EXACT). CP31/CP35 may add richer fuzzy
  location and reviewer clarification.
- `sources_json` is a JSON dump; richer source-location querying is deferred to CP35.

**Gate (run from `apps/api`):** `pytest` 305 passed / 2 skipped; `ruff check .`
All checks passed; `mypy src/` Success (67 files); `alembic upgrade head` →
`0012_requirements`; `npx tsc --noEmit` (apps/web) clean.

## ✅ ~~Checkpoint 31 — Extraction diagnostics and reconciliation history~~

**Status:** DONE — PR #36 merged.

**Plain-English outcome:** A bad extraction can be reproduced and explained.

### What we will do

1. Store parser/OCR/model/prompt/schema versions and processing-run ID.
2. Record candidate/accepted/rejected/duplicate/warning counts.
3. Track validation errors without logging full confidential bodies.
4. Correlate API→queue→worker→provider calls.
5. Record reconciliation changes when reprocessing system-generated output.

### How we will verify it

- One run ID traces the whole processing flow.
- Diagnostics distinguish parser, OCR, model, validation, and persistence failures.

### This checkpoint is complete only when

- Developers can debug why a document produced its requirement set.

### Bynd reuse notes

- **References:** `validation-service` worker runner and telemetry.
- Compute a canonical input fingerprint over everything a stage actually reads. If source/content/config changes, rerun rather than serve a stale result.
- Prefer over-processing to returning a result for the wrong input.
- Enforce a one-target-one-result invariant: every expected item gets a typed result or explicit missing/error state; duplicate/foreign results fail closed.

### Guardrail

- Do not expose provider internals/sensitive content to unauthorized users.

### Completion summary (PR #36)

**Why:** After CP28–CP31, an EXTRACT pass left audit crumbs scattered across
`processing_runs`, `extraction_runs` (per-call), `extraction_candidates`, and
one `extraction_reconciliations` summary row — but there was no single
developer-facing record that answered "why did this document produce its
requirement set?" with one query (counts, versions, rejection breakdown,
reconciliation summary). CP31 adds that diagnostics row.

**What changed:**
- `db/models.py`: `ExtractionDiagnostics` table — one row per EXTRACT
  `ProcessingRun` (unique on `processing_run_id`): `total_windows`,
  `total_llm_calls`, `total_candidates`, `accepted_candidates`,
  `rejected_candidates`, `deduped_candidates`, `promoted_requirements`,
  `ocr_warning_candidates`, plus `provider`/`model`/`prompt_version`/
  `schema_version` (captured from the audited LLM calls), a
  `rejection_breakdown` JSON (reason-code -> count, never document bodies), and
  a `reconciliation_summary` JSON (the CP29 pass summary, if reconciliation ran).
  Tenant-scoped via `document_version_id` (CASCADE). Phase 1 only — no
  vendor-compliance verdicts.
- `alembic/versions/0013_extraction_diagnostics.py` (new): `CREATE TABLE
  extraction_diagnostics` with indexes + `uq_extraction_diagnostics_run`. Head →
  `0013_extraction_diagnostics`.
- `extraction/diagnostics.py` (new, pure): `compute_diagnostics(outcome,
  *, promoted_count, reconciliation_outcome) -> ExtractionDiagnosticsSummary` —
  derives counts from an `ExtractionOutcome` (accepted = valid+persistable;
  rejected = not valid; ocr_warning = window.ocr_warning; versions from the first
  audited `LlmCallResult`).
- `document/service.py`: `capture_extraction_diagnostics(auth, document_id,
  version_number, *, run_id, outcome, reconciliation_outcome=None,
  promoted_count=0) -> ExtractionDiagnostics` — anchors on the EXTRACT run
  (tenant-scoped `get_version_or_raise` + `get_run`), computes then persists one
  row (unique per run → re-running a version's EXTRACT stage creates a new run
  → a new row = history grows, never overwrites).
- `worker/processor.py`: `_do_extract` calls `capture_extraction_diagnostics`
  after reconcile + promotion (best-effort, logs on failure, never strands the
  version) with the real `outcome`, the reconciliation result, and the promoted
  count.
- `extraction/__init__.py`: re-exports `compute_diagnostics`,
  `ExtractionDiagnosticsSummary`.

**Scope:** Diagnostics/history for the EXTRACT stage only. Does **not** add
retry semantics, per-candidate extraction history, user-facing diagnostics API,
or Phase-2 work.

**Evidence / provenance impact:** Counts are derived deterministically from
persisted `extraction_candidates` + the audited `extraction_runs` — no
document bodies are stored or logged (rejection keys are short reason codes,
per the guardrail). Provider/model/version come from the audited calls, so the
exact extraction configuration is reproducible. Because the row is unique per
processing run, reprocessing is append-only history.

**Verification:**
- `tests/test_extraction_diagnostics.py` (new, 7 pure cases): accepted/rejected/
  ocr-warning/deduped/promoted counts; rejection_breakdown grouping incl.
  unknown reason; ocr_warning independence from acceptance; versions captured
  from first call, None when no calls, captured even on a failed call;
  reconciliation wiring (deduped count + summary passthrough); no-reconciliation
  defaults.
- `tests/test_extraction_pipeline.py` (+2 `TestExtractionDiagnostics` cases):
  end-to-end `store_extraction_candidates` → `reconcile_version_candidates` →
  `persist_requirements` → `capture_extraction_diagnostics` → DB read-back of
  the exact counts (4 candidates, 3 accepted, 1 rejected w/ breakdown, 1 deduped,
  2 promoted, 0 ocr_warning, provider/model/prompt/schema from "fake" adapter,
  reconciliation summary carried through); and a second EXTRACT run (new run_id)
  writes a second diagnostics row.
- `tests/test_migration.py`: head bumped to `0013_extraction_diagnostics`;
  `extraction_diagnostics` added to `_APP_TABLES`.

**Risks / limitations:**
- Diagnostics are written once per EXTRACT run (unique constraint). A re-run
  with the SAME processing run (same run_id+stage+attempt) would violate the
  unique key — the processor never re-captures the same run in-process; CP31
  retry semantics (CP31's own "retry/re-run" item, kept as deferred here) will
  formalize re-processing as new runs.
- `accepted_candidates`/`rejected_candidates` are computed from candidate
  records *before* dedup; `deduped_candidates` reflects the reconciliation pass
  separately. This is intentional (counts measure distinct pipeline stages).
- Provider/model are taken from the first audited call; a version that mixes
  providers in one run would still report the first (CP26 logs every call
  individually for full fidelity).

**Gate (run from `apps/api`):** `pytest` 315 passed / 2 skipped; `ruff check .`
All checks passed; `mypy src/` Success (68 files); `alembic upgrade head` →
`0013_extraction_diagnostics`; `npx tsc --noEmit` (apps/web) clean.

# Stage F — Conservative normalization and structured constraints

Turn safe pieces of requirements into typed constraints without changing their meaning.

## ✅ ~~Checkpoint 32 — RequirementConstraint model and normalization states~~

**Status:** DONE — PR #37 merged.

**Plain-English outcome:** Structured values live in typed records alongside their raw fragments.

### What we will do

1. Add `RequirementConstraint`.
2. Support parameter, operator, numeric value, lower/upper bounds, unit, tolerance, qualitative condition, normalization status, raw fragment.
3. Allow more than one constraint per requirement.
4. Define SAFE/PARTIAL/NEEDS_REVIEW-style statuses.
5. Keep raw source fragment beside normalized fields.

### How we will verify it

- Schema covers exact/min/max/range/tolerance/percentage/qualitative cases.

### This checkpoint is complete only when

- Every structured value can be audited against its source fragment.

### Guardrail

- No guessed value is required just to satisfy the schema.

### Completion summary (PR #37)

**Why:** Phase 1 extraction (CP28–CP31) now produces validated requirements, but
no structured value could be modeled, audited, or compared yet. CP32 adds the
`RequirementConstraint` model + `ConstraintNormalizationState` so that
conservative numeric/qualitative constraints can live in typed records beside
their verbatim `raw_fragment` — without inferring values that aren't there.

**What changed:**
- `db/models.py`: `ConstraintNormalizationState` StrEnum
  (`UNNORMALIZED`/`SAFE`/`PARTIAL`/`NEEDS_REVIEW`) + `RequirementConstraint` table
  (many-per-requirement; FK to `requirements.id` + `document_versions.id`, both
  CASCADE; indexes). Columns: `parameter`, `operator` (String, so OCR/ambiguous
  operators are recordable without fabrication), `numeric_value`, `lower_bound`,
  `upper_bound`, `unit`, `tolerance` (all `Numeric(18,6)`, nullable),
  `qualitative_condition`, `normalization_state` (Enum, DB+Python default
  `unnormalized`), verbatim `raw_fragment`. Added `constraints` relationship on
  `Requirement` (back-populated, `delete-orphan`). Phase 1 only — no
  vendor-compliance columns.
- `alembic/versions/0014_extraction_constraints.py` (new): `CREATE TABLE
  requirement_constraints` + indexes; `normalization_state` stored as VARCHAR
  (SQLite-compatible, mirroring CP30 review_state/location_type). Head →
  `0014_extraction_constraints`.
- No service/parser changes — CP32 is model + states only (CP33 parses, CP34
  qualitatively normalizes). `compute_diagnostics`/processor unchanged.

**Scope:** `RequirementConstraint` model + normalization states only. Does
**not** parse numeric values (CP33), qualitatively normalize wording (CP34),
expose constraints via API (CP35), project the matrix (CP41), or any Phase-2
work. Parsed columns stay `NULL` at CP32 (no guessed value).

**Evidence / provenance impact:** Every constraint carries a verbatim
`raw_fragment` and a stable `requirement_id` → `requirement_sources` anchor
chain, so each structured value is auditable back to its requirement's source
pages (CP30/CP35). `normalization_state` is never silently advanced — values
start `UNNORMALIZED` and only CP33/CP34 transition them, preserving the
"unreviewed uncertainty presented as certain" guardrail.

**Verification:**
- `tests/test_extraction_constraint.py` (new, 9 cases): states are the closed
  Phase-1 set with stable string values; column-level default is
  `unnormalized` (Python + DB server_default) and parsed fields are nullable;
  full field set round-trips on a transient instance; multi-constraint
  relationship grouping; DB round-trip for every `ConstraintNormalizationState`
  (read-back == set enum member, raw_fragment verbatim, back-populated parent);
  insert-without-state still yields `UNNORMALIZED`.
- `tests/test_migration.py`: head bumped to `0014_extraction_constraints`;
  `requirement_constraints` added to `_APP_TABLES`.

**Risks / limitations:**
- No parsing yet — `numeric_value`/`operator`/etc. remain `NULL` until CP33/CP34.
  The matrix (CP41) skips NULL-value constraints.
- `operator` is a free `String` at CP32 (operators are validated/normalized in
  CP33's parser, not the schema).

**Gate (run from `apps/api`):** `pytest` 324 passed / 2 skipped; `ruff check .`
All checks passed; `mypy src/` Success (68 files); `alembic upgrade head` →
`0014_extraction_constraints`; `npx tsc --noEmit` (apps/web) clean.

## ⬜ Checkpoint 33 — Deterministic numeric/operator/unit parsing

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Obvious mathematical structure is parsed in code and ambiguous values escalate.

### What we will do

1. Parse `=`, `<`, `≤`, `>`, `≥`, min/max, ranges, percentages, scientific notation.
2. Handle decimal/thousands separators conservatively.
3. Preserve lexical source form.
4. Parse units and tolerances without converting them yet.
5. Keep distinctions such as accuracy/resolution/precision/repeatability/sensitivity/range separate.
6. Escalate ambiguous OCR/operator/unit cases.

### How we will verify it

- Tests cover boundary operators, negatives, decimals, ranges, percentages, unit-bearing values, OCR-corrupted symbols.

### This checkpoint is complete only when

- Accepted numeric normalization is deterministic and reproducible.

### Bynd reuse notes

- **Reference:** `ocr-table-fixes-discovery`.
- High-confidence neighboring cells may provide formatting context for ambiguous table numbers, but only as supporting context.
- Any ambiguous decimal/thousands/glyph interpretation must retain original text and be flagged. Tender Compliance is intentionally stricter than that fixer: diagnostic suggestions are allowed; silent correction is not.

### Guardrail

- Do not use an LLM as the final authority for simple math parsing.

## ✅ ~~Checkpoint 34 — Qualitative normalization and ambiguity escalation~~

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Wording becomes easier to review without becoming broader/stronger than the source.

### What we will do

1. Generate conservative normalized wording.
2. Preserve subject, obligation, conditions, scope, and negation.
3. Extract qualitative conditions only when explicit.
4. Propagate OCR/structure uncertainty.
5. Set OCR_WARNING/NEEDS_CLARIFICATION where meaning is unsafe.
6. Version normalization rules/prompts separately.

### How we will verify it

- Examples cover certifications, environmental conditions, interfaces, documentation, and qualitative performance.
- Meaning-changing OCR cases escalate.

### This checkpoint is complete only when

- Normalized text is useful but every unsafe rewrite is visibly unresolved.

### Guardrail

- Do not turn descriptive prose into a mandatory obligation.

# Stage G — Persistent human review and real source verification

Replace demo state with auditable review actions against the actual tender source.

## ✅ Checkpoint 35 — Requirement list/detail API

**Status:** DONE — merged PR #41 (`cp35/requirement-api`).

**Plain-English outcome:** The frontend can load real requirements, filters, constraints, and sources.

### What we did

1. Added project-scoped requirement list (`GET /projects/{project_id}/documents/{document_id}/versions/{version_number}/requirements`).
2. Added detail endpoint (`GET .../requirements/{requirement_id}`).
3. Stable ordering by `created_at` desc + `id` for deterministic pagination.
4. Filters for `review_state`, `requirement_type`, and case-insensitive `search`.
5. Detail response returns sources/constraints/revision summary; list response omits `raw_source` and constraints (guardrail satisfied).
6. Every query authorized by organization (membership verification via `get_version_or_raise`).

### How we verified it

- API tests cover ordering, filtering, empty lists, pagination, search, detail (full info, 404, tenant isolation), and stable ordering. 10 new tests.
- `ruff check .` clean, `mypy src/` clean (71 source files).
- Full suite: 546 passed, 2 skipped. CI (api + web) green.

### Guardrail

- List responses never include full document bodies or `raw_source`.

## ✅ Checkpoint 36 — Real PDF/source viewer with trustworthy highlights

**Status:** DONE — merged PR #43 (`cp36/source-viewer`).

**Plain-English outcome:** Clicking a citation opens the actual uploaded source page and shows the known source location.

### What we did

1. **Serves stored PNG page renders** (CP20) via `GET .../pages/{page_number}/image` — no PDF.js integration; PNG bytes streamed from object storage with `media_type=image/png` and cache headers.
2. **Opens exact immutable document version/page** — all routes are tenant-scoped via `get_version_or_raise`.
3. **Overlay exact bounding boxes** from `RequirementSource.bbox` via `GET .../pages/{page_number}/sources` — bboxes are only rendered when they exist (never fabricated). Exact anchors get solid borders; approximate anchors get dashed borders.
4. **Fallback to text-only view** when no rendered image is available (404 on `/image` → `has_image=false` → text fallback with labeled "Text-only fallback" state). Source text snippets from anchors are shown with explicit "Exact"/"Approximate" labels.
5. **Zoom and asynchronous render** — zoom in/out/reset controls (50%–200% range), image loading state with shimmer placeholder.
6. **Frontend `SourceViewer` component** (`components/source-viewer.tsx`) — renders the page PNG in a relative-positioned container with absolutely-positioned overlay rectangles. `imageScale` is computed on image load to map natural-image bbox coordinates to displayed coordinates. Page navigation (prev/next) via `onPageChange` callback.

### How we verified it

- API tests: page metadata (returns, no-image fallback, 404, tenant isolation), page image (returns bytes, 404 when no image, tenant isolation), source anchors (returns anchors with bbox, empty for no anchors, tenant isolation). 10 new tests.
- `ruff check .` clean, `mypy src/` clean (72 source files).
- Frontend: `tsc --noEmit` clean, `next build` successful.
- Full suite: 556 passed, 2 skipped. CI (api + web) green.

### Bynd reuse notes

- Standardized viewer inputs around immutable document version + page + one-or-more source spans/quotes/bboxes.
- Exact/approximate locations are visibly distinct (solid vs. dashed borders).
- If exact highlighting fails but the page is trusted, the viewer shows the page + text-only fallback with explicit "Approximate" label rather than inventing a box.

### Guardrail

- Do not present reconstructed text as the original PDF image. Served only real rendered PNG bytes; text-only fallback is explicitly labeled as such.

## ✅ Checkpoint 37 — Wire the three-pane review UI to real APIs

**Status:** DONE — merged PR #45 (`cp37/review-ui`).

**Plain-English outcome:** The existing interaction model becomes the real product instead of a demo.

### What we did

1. Removed demo seed data (`seedRequirements`) from real project routes — `TenderReviewWorkspace` now accepts `projectId`/`documentId`/`version` props and fetches from the API.
2. Loads requirements via `api.fetchRequirements` (CP35 list), selected requirement detail via `api.fetchRequirement` (CP35 detail) with constraints and sources.
3. Selection/deep-link state is in component state (URL deep-linking deferred).
4. Shows loading shimmer, API error state, no-requirements state, and detail-loading state — no fake fallback on backend failure.
5. Uses real document/version/page labels from API responses.
6. `DemoTenderReviewWorkspace` kept as an isolated fixture for the demo route (`/projects/demo`); real project routes never fall back to demo data.

### How we verified it

- API: `ruff check .` clean, `mypy src/` clean (72 source files), 556 tests pass.
- Web: `tsc --noEmit` clean, `next build` successful (new `/projects/[id]/review` route generated).
- Review workspace link unhidden on project page.

### Guardrail

- Never hide backend failure by rendering demo data. The real workspace shows explicit error/empty states; demo seed data is only on the isolated `/projects/demo` route.

## ⬜ Checkpoint 38 — Requirement edit and immutable revision history

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Reviewers can correct normalized text without erasing how it changed.

### What we will do

1. Add `RequirementRevision`.
2. Create edit service/API.
3. Create a revision for material edits.
4. Keep raw source unchanged when editing normalized text.
5. Handle stale/concurrent edits explicitly.
6. Write audit events.
7. Show history metadata in the UI.

### How we will verify it

- Edit→refresh persists new wording and previous revision.
- Concurrent update behavior is tested.

### This checkpoint is complete only when

- A reviewer can answer what changed, when, and by whom.

### Guardrail

- Editing normalized wording must not overwrite evidence/source text.

## ⬜ Checkpoint 39 — Split, merge, delete/supersede, categories, ordering, mandatory, and notes

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** A reviewer can repair extraction structure and organize the final matrix without losing lineage.

### What we will do

1. Add `RequirementRelation` for SPLIT_INTO/MERGED_INTO/SUPERSEDES.
2. Split with explicit source assignment.
3. Merge while preserving all contributing sources.
4. Treat mistaken extractions as superseded/deleted auditable state rather than erasing history where required.
5. Add category hierarchy/assignment.
6. Persist stable sort order.
7. Keep mandatory tri-state/nullable unless source supports true/false.
8. Persist reviewer notes separately from source.
9. Audit every material mutation.

### How we will verify it

- Split/merge tests preserve provenance.
- Reorder/category/notes/mandatory survive refresh.
- Superseded rows are excluded from normal matrix output but auditable.

### This checkpoint is complete only when

- The user can correct extraction granularity and organization entirely inside the product.

### Guardrail

- Never merge multiple source fragments into one fake contiguous citation.

## ⬜ Checkpoint 40 — Review-state machine, audit timeline, and real progress counts

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** The review queue and dashboard accurately reflect outstanding human work.

### What we will do

1. Implement UNREVIEWED/REVIEWED/NEEDS_CLARIFICATION/OCR_WARNING transitions.
2. Define initial/system transition rules.
3. Define mark-reviewed/reopen/escalate behavior.
4. Prevent review completion when required uncertainty remains unless an explicit audited override exists.
5. Add project/requirement audit query APIs.
6. Render a lightweight audit/history timeline.
7. Compute real processed/reviewed/unresolved counts.
8. Make next/previous unresolved navigation use persisted state.

### How we will verify it

- Transition tests cover allowed/forbidden paths.
- Dashboard counts match database queries.
- Audit timeline reconstructs edits/splits/reviews.

### This checkpoint is complete only when

- 'Needs review' is a trustworthy queue, not a UI-only flag.

### Guardrail

- These are review states, not compliance states.

# Stage H — Phase 1 matrix and export

Produce the clean, auditable tender requirement deliverable.

## ⬜ Checkpoint 41 — Canonical Phase 1 matrix projection and screen

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** One deterministic projection powers both the matrix UI and export.

### What we will do

1. Project columns: S.No., Requirement ID, Tender Requirement, Category, Clause, Source Page, Mandatory, User Notes, Review Status.
2. Use current non-superseded requirement state.
3. Preserve explicit ordering.
4. Represent missing source fields honestly.
5. Add Matrix tab using this projection.
6. Link rows back to requirement/source review.
7. Highlight unresolved statuses.
8. Do not add vendor compliance columns.

### How we will verify it

- Projection tests cover null metadata, ordering, multi-source rows, superseded rows.
- UI values match API/projection values.

### This checkpoint is complete only when

- Users can inspect exactly what will be exported.

### Guardrail

- Do not duplicate matrix business logic in frontend and export separately.

## ⬜ Checkpoint 42 — XLSX export, history, download, and failure handling

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Reviewed requirements become a professional, versioned Excel deliverable.

### What we will do

1. Use server-side `openpyxl`.
2. Use the canonical matrix projection.
3. Add project/tender ID and generation timestamp.
4. Apply readable widths/wrapping/frozen headers/filters.
5. Preserve source references and ordering.
6. Store export metadata and artifact.
7. Add create/list/download endpoints.
8. Record actor/source state/version/time.
9. Keep multiple historical exports.
10. Surface failures and safe retry.
11. Indicate when project requirements changed after an older export.

### How we will verify it

- Workbook opens in common spreadsheet tools.
- Structural/golden tests verify columns, ordering, values, source references.
- Failed export never appears successful.

### This checkpoint is complete only when

- A reviewed project can produce/download a clean XLSX without manual spreadsheet assembly.

### Bynd reuse notes

- **References:** `ExcelTableCreator` and `metric-search` workbook review/export patterns.
- Keep export formatting deterministic and config-driven where practical.
- Consider Excel notes/highlights for unresolved review states or reviewer/source context only when they improve the deliverable and come from the canonical matrix projection.
- Presentation must never mutate values, infer compliance, or become a second business-logic implementation.

### Guardrail

- Do not add formulas/conversions that modify tender meaning.

# Stage I — Phase 1 evaluation, security, operations, deployment, and release

Prove the product is trustworthy under realistic tenders before starting vendor compliance.

## ⬜ Checkpoint 43 — Curated Phase 1 benchmark dataset

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Extraction quality has a repeatable ground truth.

### What we will do

1. Collect safe representative tender fixtures.
2. Annotate gold requirements, source page/region, split/grouping, safe normalization, expected review state.
3. Include min/max/exact/ranges/tolerances/percentages/units.
4. Include tables, nested clauses, multi-page requirements, scans, repeated headers, duplicates, missing coordinates.
5. Include OCR symbol corruption and ambiguous terminology.
6. Version source identity and annotator notes.

### How we will verify it

- Every benchmark item has expected outputs/provenance.
- Dataset includes hard/adversarial cases.

### This checkpoint is complete only when

- Parser/model changes can be compared on the same ground truth.

### Bynd reuse notes

- **References:** `validation-engine/evals`, `validation-service/evals`, and `Evals_dataset`.
- Layer the benchmark into real/golden positives, real/golden negatives, mutation-generated negatives, historical regressions, broad stress/adversarial cases, and small public-API/invariant contracts.
- Generate meaning-bearing mutations for numbers, units, operators, years, entities/scope, OCR characters, and source/page authority rather than hand-authoring every negative.
- Every confirmed production failure should become a regression case.

### Guardrail

- Do not use confidential customer material without permission.

## ✅ ~~Checkpoint 44 — Automated evaluation harness and quality gates~~

**Status:** DONE — PR #53

**Plain-English outcome:** Release decisions use measured precision/recall/provenance fidelity instead of screenshots.

### What we will do

1. Measure requirement precision/recall.
2. Measure split/group accuracy and duplicate rate.
3. Measure invented-requirement rate.
4. Measure page/clause/source-text/location accuracy.
5. Measure numeric/unit/operator/range fidelity and false normalization.
6. Measure OCR warning/escalation behavior.
7. Record parser/OCR/model/prompt/schema versions for every eval.
8. Create human-readable and machine-readable reports.
9. Put a small regression set in CI and run full evals on controlled changes.
10. Set conservative release thresholds.

### How we will verify it

- A deliberately broken extractor causes expected metric regression.
- Same config/dataset is reproducible within known model variance.

### This checkpoint is complete only when

- High-risk false extraction/citation regressions block release.

### Bynd reuse notes

- **Reference:** `validation-engine/evals`.
- Add before-vs-after eval comparison and a compact correctness report/dashboard with case category, expected vs actual, reason code, and regression delta.
- Optimize for coverage of failure classes, not a vanity test count.
- Keep hard invariants as separate gates so a severe false-positive class cannot be averaged away by a good aggregate score.

### Guardrail

- Do not hide false positives inside one average score.

## ⬜ Checkpoint 45 — Adversarial documents, tenant security, upload security, and prompt-injection tests

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Known dangerous inputs fail safely instead of becoming confident wrong output.

### What we will do

1. Test comparison symbols, decimal points, units, Greek symbols, rotated pages, merged tables, page breaks, duplicated headers.
2. Test malformed/protected PDFs and resource abuse cases.
3. Test prompt-injection content inside source documents.
4. Run cross-tenant API tests for every tenant-owned resource.
5. Enforce production malware scanning and worker isolation/resource limits.
6. Review LLM provider retention/training/confidentiality settings.
7. Use secret management in deployment.
8. Add dependency/security scanning as appropriate.

### How we will verify it

- Document instructions cannot override system rules or invoke tools.
- Org A cannot access Org B resources.
- Malicious/unsupported files do not enter normal processing.

### This checkpoint is complete only when

- The security model has tested controls, not only documentation.

### Bynd reuse notes

- **Reference:** `universal-auth-service`.
- Add explicit security headers/CSP, trusted-origin rules, open-redirect protection, request IDs, and rate limiting where the deployed surface needs them.
- Development localhost allowances must never leak into production origin/redirect configuration.
- Security middleware must not log bearer tokens, secrets, or document content.

### Guardrail

- Frontend hiding is never authorization.

## ⬜ Checkpoint 46 — Observability, performance, resource, cost, retention, backup, and deletion

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** The system can be operated, debugged, cost-controlled, restored, and safely deleted.

### What we will do

1. Standardize structured logs with request/job correlation IDs.
2. Record stage duration, provider/version, retries, validation failures, counts, export outcomes.
3. Add metrics for queue depth/failures/latency/review backlog.
4. Avoid full confidential document bodies in normal logs.
5. Set upload/page/time/memory/concurrency limits.
6. Track LLM token/cost metadata when available.
7. Profile large tenders and requirement lists.
8. Define retention for originals, rendered assets, OCR/parser output, exports, later embeddings.
9. Implement authorized hard deletion.
10. Keep audit retention policy separate when needed.
11. Define database/object-storage backup strategy.
12. Test restore with non-production data.

### How we will verify it

- A failed job is traceable end to end by IDs.
- Hard-delete removes the expected tenant content only.
- Backup restore yields consistent metadata/object references.

### This checkpoint is complete only when

- Operators can explain failure, performance, cost, retention, deletion, and recovery behavior.

### Bynd reuse notes

- **References:** `validation-service/telemetry.py`, `engineering-docs/llm-cost-logging-sop.md`, and `finance-data-ingestion-service`.
- Use privacy-safe telemetry allowlists: IDs, stage, timing, counts, model/provider metadata, retry category, token usage, and status are allowed; prompts, source text, URLs, provider payloads, and raw exception messages are not normal log fields.
- Classify provider failures into stable categories such as timeout, rate-limit/quota, authentication, billing, malformed response, and unavailable provider; retry only known transient classes.
- Detect provider/schema drift explicitly rather than silently dropping renamed/new fields.
- Every LLM run gets per-call usage plus one run summary so cost can be answered from logs without rerunning work.

### Guardrail

- Do not promise provider-side deletion/retention behavior that is not actually configured.

## ⬜ Checkpoint 47 — Deployment configuration and runbook

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** API, web, worker, migrations, storage, queue, and database can be deployed reproducibly.

### What we will do

1. Define production environment configuration.
2. Define API/web/worker process commands and health checks.
3. Run migrations explicitly during deployment.
4. Configure secure Postgres/Redis/object storage/TLS/CORS/secrets.
5. Document rollback for app/schema changes.
6. Document failed-job recovery and worker scaling.
7. Add deployment smoke tests.
8. Keep application provider abstractions even if the first deployment uses one cloud.

### How we will verify it

- A clean environment can be deployed from the documented runbook.
- Rollback/recovery paths are testable.

### This checkpoint is complete only when

- Deployment no longer depends on manual database edits or the original developer's laptop.

### Bynd reuse notes

- **References:** `bynd-devops-system` and deployed Bynd job services.
- Prefer GitHub OIDC/workload identity over long-lived cloud credentials when supported.
- Deploy immutable environment + git-SHA image tags; `latest` is only a convenience alias.
- Separate staging/production config and secrets.
- Run migrations before new API deployment. Use an environment-local migration job for private databases.
- Long-running APIs/web map naturally to Container Apps; one-document queue workers may later map to Container Apps Jobs/KEDA when measured load justifies it. Keep the MVP queue adapter provider-neutral.

### Guardrail

- Do not hide manual undocumented steps in release operations.

## ⬜ Checkpoint 48 — Phase 1 end-to-end acceptance and release gate

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** The exact PRD journey works from a clean environment and meets conservative quality thresholds.

### What we will do

1. Create project.
2. Upload real digital and scanned tenders.
3. Process pages/OCR.
4. Extract requirements with source anchors.
5. Normalize safely.
6. Review/edit/split/merge/categorize/reorder/resolve warnings.
7. Open representative cited sources.
8. Generate matrix.
9. Export XLSX.
10. Inspect audit history and failure states.
11. Run benchmark/eval thresholds.
12. Review open high-severity bugs/security findings.
13. Verify deployment/backup/retention runbooks.
14. Document released component versions and known limitations.

### How we will verify it

- Acceptance needs no database intervention.
- No Phase 1 step claims OEM/vendor compliance.
- False extraction/citation metrics meet the release bar.

### This checkpoint is complete only when

- Phase 1 is a trustworthy end-to-end product loop, not a set of disconnected components.

### Guardrail

- Do not waive wrong-citation/invented-requirement issues merely to declare Phase 1 done.

# Stage J — OEM evidence, deterministic comparison, compliance review, and final submissions

Extend the proven source-preserving pipeline to vendor/OEM evidence and produce conservative, human-approved compliance outputs.

## ⬜ Checkpoint 49 — OEM document ingestion and provenance

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Datasheets, brochures, manuals, certificates, proposals, test reports, quotations, and other OEM material use immutable source versioning.

### What we will do

1. Add OEM document/version entities only when this checkpoint begins.
2. Reuse organization/project authorization and object storage.
3. Add OEM document type/product/vendor metadata.
4. Reuse upload validation, status, queue, parsing, rendering, OCR, pages, retries, and audit patterns.
5. Add OEM upload/document UI separated from tender source documents.
6. Keep exact version identity for every later evidence citation.

### How we will verify it

- OEM documents process without corrupting tender entities.
- Versions remain immutable and tenant-scoped.

### This checkpoint is complete only when

- A project can hold both tender requirements and source-preserving OEM materials.

### Guardrail

- Tender and OEM sources must remain distinguishable.

## ⬜ Checkpoint 50 — Evidence model, retrieval/indexing, and retrieval evaluation

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** The system can find likely OEM evidence while treating retrieval failure as missing evidence, not non-compliance.

### What we will do

1. Add `Evidence` and `EvidenceLocation` with immutable OEM document version/page/source text/offset/bbox/location precision/OCR confidence.
2. Allow multiple evidence locations per requirement.
3. Create searchable OEM text segments tied to locations.
4. Start with deterministic metadata/text search; add embeddings/hybrid retrieval only when evaluation shows value.
5. If embeddings are needed, prefer a simple Postgres/pgvector-style approach before a separate vector platform.
6. Record retrieval query/config/version/ranking signals.
7. Return several evidence candidates with source metadata.
8. Build retrieval benchmark precision/recall.
9. Define zero/weak retrieval as missing evidence.

### How we will verify it

- Every candidate opens its actual OEM source.
- Retrieval precision/recall is measurable.
- No-result cases never become automatic NON_COMPLIANT.

### This checkpoint is complete only when

- The system can propose source-linked evidence candidates for a requirement.

### Bynd reuse notes

- **References:** `validation-service` and `validation-engine`.
- Retrieval/evidence output needs typed outcomes and stable reason codes, not a boolean. Distinguish evidence found, source unavailable, out of scope, malformed input, retrieval failure, and genuinely absent/contradictory evidence.
- Every requested requirement gets a result or explicit missing/error record; silence is never a verdict.

### Guardrail

- Semantic similarity is not proof.

## ⬜ Checkpoint 51 — Evidence review UI and evidence curation

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Humans can inspect, accept, reject, add, or remove evidence before assessment.

### What we will do

1. Show tender requirement beside OEM source viewer and evidence candidates.
2. Show document version/page/location precision/OCR warnings.
3. Allow accept/reject/add/remove.
4. Keep retrieval score visually secondary to source content.
5. Audit curation.
6. Make assessment inputs use the curated evidence set or clearly label unreviewed system candidates.

### How we will verify it

- Every accepted evidence item is viewable in context.
- Changing evidence set deterministically changes assessment inputs.

### This checkpoint is complete only when

- There is no hidden evidence candidate being treated as approved proof.

### Guardrail

- High retrieval score must never be shown as compliant.

## ⬜ Checkpoint 52 — Vendor specification extraction

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Accepted OEM evidence becomes structured vendor facts without losing its supporting source.

### What we will do

1. Add vendor-spec schema for parameter/concept, value/range, unit, tolerance/qualitative statement, entity/model, conditions, evidence IDs.
2. Use deterministic parsing for explicit numbers/operators.
3. Use structured LLM interpretation only for language/context not safely handled by rules.
4. Preserve distinctions such as resolution vs accuracy.
5. Require every persisted vendor fact to point to evidence.
6. Escalate OCR/ambiguity.

### How we will verify it

- Benchmark includes same number/different metric/entity/scope cases.
- Unsupported values cannot persist without evidence.

### This checkpoint is complete only when

- A structured vendor fact can always be traced back to OEM source material.

### Guardrail

- Do not infer a missing specification from marketing language.

## ⬜ Checkpoint 53 — Deterministic unit normalization and specification comparison engine

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Comparable tender/vendor values are evaluated in code with explicit rules.

### What we will do

1. Use a tested unit library such as Pint behind a domain interface.
2. Map safe aliases while keeping original text.
3. Check dimensional compatibility before conversion.
4. Handle prefixes, percentages, temperature, compound units, tolerances carefully.
5. Implement exact/min/max/inclusive-exclusive/range containment-overlap/tolerance comparisons.
6. Require matching parameter/concept, entity/model, scope, and operating condition before comparing.
7. Return typed outcomes and conversion/comparison reasons.
8. Keep qualitative cases out of numeric math.
9. Add boundary-equality and wrong-metric same-number adversarial tests.

### How we will verify it

- Unit-conversion benchmark passes supported units.
- Incompatible dimensions are rejected.
- Accuracy vs resolution cannot pass because a number happens to match.

### This checkpoint is complete only when

- Every supported numeric outcome explains operands, conversions, comparison rule, and result.

### Guardrail

- An LLM may not overrule deterministic math.

## ⬜ Checkpoint 54 — ComplianceAssessment model and status semantics

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Compliance states exist only after evidence and deterministic comparison are real.

### What we will do

1. Add `ComplianceAssessment` tied to requirement/evidence/comparison/assessment version/reviewer state.
2. Use `COMPLIANT`, `NON_COMPLIANT`, `PARTIAL`, `NOT_DEMONSTRATED`, `CONFLICT`, `HUMAN_REVIEW_REQUIRED` unless the product contract is explicitly changed.
3. Document precise criteria.
4. Separate system suggestion from final human approval where needed.
5. Version assessments when evidence/specifications change.
6. Audit transitions/overrides.

### How we will verify it

- Status criteria are testable.
- Missing evidence maps to NOT_DEMONSTRATED/HUMAN_REVIEW according to rules, not NON_COMPLIANT.

### This checkpoint is complete only when

- Two engineers can interpret every status consistently and trace it to inputs.

### Bynd reuse notes

- **Reference:** `validation-service/docs/OUTPUT_CONTRACT.md`.
- Keep the six product statuses, but pair each system assessment with a stable machine-readable `reason_code` plus explanatory text.
- A negative status is allowed only when evidence supports a negative conclusion. If the engine cannot honestly evaluate, use `HUMAN_REVIEW_REQUIRED` / `NOT_DEMONSTRATED` according to the product rule—not `NON_COMPLIANT`.
- Engine/provider failures should degrade to typed unresolved assessments rather than fabricated verdicts wherever the workflow can safely continue.

### Guardrail

- Do not replace evidence with a generic confidence score.

## ⬜ Checkpoint 55 — Evidence-backed qualitative reasoning

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Language reasoning is limited to cited facts and cannot invent support.

### What we will do

1. Provide only the tender requirement plus cited/accepted facts needed for judgment.
2. Use strict structured labels for support/mismatch/unsupported/conflict/insufficient evidence.
3. Require every material explanation claim to come from supplied evidence.
4. Keep deterministic numeric results authoritative.
5. Record model/prompt/version/evidence IDs.
6. Prefer HUMAN_REVIEW_REQUIRED/NOT_DEMONSTRATED when evidence is incomplete.
7. Evaluate attribution/scope/time/entity mismatch and source contradiction.

### How we will verify it

- Model cannot cite a source not supplied.
- Evaluation includes quantitative mismatch, attribution mismatch, source contradiction, unsupported claims, insufficient evidence.

### This checkpoint is complete only when

- Qualitative assessments are source-bounded and auditable.

### Bynd reuse notes

- **Reference:** `validation-service` visual/judge contracts.
- A model asserting a mismatch/unsupported claim must return source-grounded observed evidence or a structured exact mismatch; otherwise downgrade to unresolved review.
- Preserve explicit `cannot_tell`/abstention as a first-class safe outcome.
- Deterministic numeric/comparison results remain authoritative and cannot be overridden by model confidence.

### Guardrail

- Never ask an unconstrained model 'does this product comply?' and accept the answer.

## ⬜ Checkpoint 56 — Conflict and contradiction detection

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Conflicting vendor claims are surfaced instead of silently choosing the convenient one.

### What we will do

1. Compare facts for same parameter/entity/condition across OEM sources.
2. Detect tender-vendor concept mismatches and OEM-OEM contradictions.
3. Preserve both/all conflicting sources.
4. Set CONFLICT/HUMAN_REVIEW according to rules.
5. Show conflicts side by side.
6. Cover cases where a compliance sheet says YES but a datasheet reports a different technical metric/value.

### How we will verify it

- Fixtures include same-number/different-claim and different-number/same-parameter conflicts.
- System never resolves conflict by discarding inconvenient evidence.

### This checkpoint is complete only when

- Reviewers can see exactly what conflicts and where each value came from.

### Bynd reuse notes

- **Reference:** `industry-report-agentic` multi-lane verdict merging.
- Merge multiple evidence/comparison/reasoning lanes by stable requirement ID.
- If authoritative lanes disagree, surface CONFLICT; never silently pick by priority, set union, or arrival order.
- Do not take irreversible actions on contradictory signals.

### Guardrail

- Conflict is not automatically non-compliance.

## ⬜ Checkpoint 57 — Missing evidence, clarification questions, and deviations

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Unresolved gaps become precise workflow items instead of false compliance/non-compliance.

### What we will do

1. Represent missing/insufficient evidence explicitly.
2. Generate clarification only for a specific gap, ambiguity, or conflict.
3. Reference exact requirement and missing/conflicting fact.
4. Add `ClarificationRequest` lifecycle.
5. Add `Deviation` records for known departures with evidence/notes.
6. Allow human editing/approval of generated clarification text.
7. Audit lifecycle changes.

### How we will verify it

- No-evidence case produces a precise clarification/not-demonstrated path.
- Clarification is not a generic 'please confirm compliance' message.

### This checkpoint is complete only when

- Every unresolved requirement has a specific, reviewable next action.

### Bynd reuse notes

- **Reference:** `validation-service` typed abstention model.
- 'Could not evaluate' describes the checker, not the product.
- Pass stable reason codes such as missing source, ambiguous value/unit/entity, conflicting sources, and unreadable evidence into clarification generation so questions are specific.

### Guardrail

- Do not turn missing evidence into a negative technical claim.

## ⬜ Checkpoint 58 — Human compliance review and audit

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** A reviewer controls the final assessment state and can see all evidence/comparison history.

### What we will do

1. Allow accept/reject system assessment.
2. Allow status override with reason.
3. Allow add/remove evidence.
4. Allow comments and reopen.
5. Show deterministic comparison details.
6. Show conflict/clarification/deviation state.
7. Version material assessment changes.
8. Audit every approval/override.

### How we will verify it

- Assessment history survives refresh and evidence changes.
- Override reason/actor/time are queryable.

### This checkpoint is complete only when

- Final status is an auditable human-reviewed decision, not an opaque model result.

### Guardrail

- Never erase the original system assessment/evidence when a human overrides it.

## ⬜ Checkpoint 59 — Final compliance matrix and submission projection

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** The matrix expands from tender requirements into evidence-backed vendor-response rows while preserving original source columns.

### What we will do

1. Keep original tender columns.
2. Add vendor response/specification fields.
3. Add evidence citations.
4. Add assessment status.
5. Add deviation and clarification state.
6. Add reviewer/approval metadata where appropriate.
7. Use one canonical final projection for UI and exports.
8. Keep unresolved requirements visible.

### How we will verify it

- Final matrix rows trace to tender source plus OEM evidence/assessment versions.
- UI and export use the same projection.

### This checkpoint is complete only when

- The matrix is the authoritative submission view, not a separate manually edited spreadsheet.

### Guardrail

- Do not hide unresolved/not-demonstrated/conflict rows.

## ⬜ Checkpoint 60 — Final XLSX, DOCX, and PDF outputs

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** Approved submission data can be exported into deliverables without losing evidence/version metadata.

### What we will do

1. Extend XLSX export using the final projection.
2. Add DOCX export only after the final data model is stable.
3. Add PDF generation from a controlled template/render path.
4. Include evidence references and source document/version metadata.
5. Preserve ordering and approved wording.
6. Store every generated artifact immutably with metadata.
7. Never mutate an older generated submission in place.

### How we will verify it

- Outputs open correctly and contain expected traceability fields.
- Export tests compare key values/status/evidence/version metadata.

### This checkpoint is complete only when

- A reviewer can generate all required submission formats from approved product state.

### Guardrail

- Do not let document templates invent or recompute compliance facts.

## ⬜ Checkpoint 61 — Approval, locking, submission versions, Phase 2 evaluation, and production release

**Status:** NOT STARTED unless a merged PR updates this file.

**Plain-English outcome:** A signed-off submission becomes immutable, measurable, and safe to release.

### What we will do

1. Add approval/lock state for a submission version.
2. After lock, later changes create a new submission version.
3. Record approver/time/source assessment versions.
4. Build Phase 2 benchmark data.
5. Measure evidence retrieval precision/recall, unit conversion, numeric comparison, classification, citation correctness, conflict recall, hallucination, false non-compliance, and especially false compliance.
6. Give false compliance the highest release severity.
7. Run OEM security/tenant/provider/retention review.
8. Run end-to-end acceptance: tender → requirements → OEM docs → evidence → comparisons/reasoning → conflicts/gaps → human approval → final exports.
9. Review performance/cost/observability at production scale.
10. Release only when quality/security thresholds and known high-severity issues are acceptable.

### How we will verify it

- Locked submissions cannot silently change.
- Every final compliance statement traces to evidence or is explicitly unresolved.
- False-compliance metric is reported separately and gates release.

### This checkpoint is complete only when

- The complete product workflow is evidence-backed, human-approved, versioned, exportable, evaluated, and production-operable.

### Guardrail

- Never trade false compliance for a better-looking completion rate.

# Plan completion rule

The plan is complete only when CP00 through CP61 are checked and crossed out, the relevant end-to-end acceptance tests pass, release gates meet conservative quality/security thresholds, and every final compliance statement is either evidence-backed or explicitly unresolved.

If the product direction changes, update this file through a focused PR, explain why, and continue from the new first unchecked checkpoint.
