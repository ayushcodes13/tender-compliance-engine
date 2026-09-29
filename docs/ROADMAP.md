# Roadmap

The roadmap is intentionally milestone-driven. Each milestone should work before the next layer is added.

## M0 — Repository foundation

- monorepo structure
- backend/frontend skeletons
- local infrastructure
- environment configuration
- CI skeleton
- health endpoint
- product/architecture/security docs

**Exit:** repository boots locally and the API health test passes.

## M1 — Project model

- PostgreSQL integration
- migrations
- organization/project tables
- create/list/get project API
- basic project UI
- audit foundation

**Exit:** user can create and reopen a project; tests cover authorization boundaries and state transitions.

## M2 — Tender upload + versioning

- upload API
- file validation
- immutable object storage
- SHA-256 deduplication metadata
- tender document/version records
- processing states
- upload UI

**Exit:** original tender is safely stored and versioned; no parsing yet required.

## M3 — Document parsing/OCR

- PDF parser adapter
- page model
- scanned-page detection
- OCR adapter
- rendered page assets
- page text/metadata persistence
- retry/failure handling

**Exit:** every processable page has a source-preserving representation and failures are explicit.

## M4 — Requirement extraction

- structured extraction schema
- extraction prompt/version tracking
- chunk/window strategy
- duplicate/header/footer handling
- multi-requirement splitting
- parent-child clause support
- provenance persistence

**Exit:** extracted rows are traceable to source pages and invalid model output cannot be persisted as valid requirements.

## M5 — Requirement normalization

- structured parameter/operator/value/unit representation
- conservative normalization statuses
- OCR/ambiguity review flags
- no silent unit conversion

**Exit:** safely normalizable constraints become structured without changing source meaning.

## M6 — Human review UX

- requirements table
- requirement detail panel
- source page viewer
- edit/split/merge/reorder/category/notes
- review states
- revision + audit history

**Exit:** a reviewer can correct extraction without losing provenance or edit history.

## M7 — Compliance matrix + Excel export

- matrix projection
- ordering
- export service
- XLSX formatting
- export audit event

**Exit:** reviewed tender requirements export cleanly to an Excel compliance matrix with source references.

## M8 — Phase 1 evaluation + hardening

- realistic benchmark dataset
- extraction/citation metrics
- OCR adversarial cases
- security review
- observability
- deployment runbook

**Exit:** known quality levels are measured rather than guessed.

---

# Phase 2 — only after Phase 1 works

## M9 — OEM document ingestion

Reuse document/version/page provenance for datasheets, manuals, certificates, proposals, test reports, and other OEM material.

## M10 — Evidence retrieval

Source-preserving retrieval with document/page/section/coordinates and retrieval confidence. Retrieval failure means missing evidence, not non-compliance.

## M11 — Deterministic specification engine

Parse and compare thresholds, ranges, tolerances, percentages, and compatible units in code.

## M12 — Evidence-backed compliance reasoning

Add `COMPLIANT`, `NON_COMPLIANT`, `PARTIAL`, `NOT_DEMONSTRATED`, `CONFLICT`, and `HUMAN_REVIEW_REQUIRED` only when the evidence architecture and tests support them.

## M13 — Contradictions + clarifications

Detect conflicting values/concepts/documents and generate precise OEM clarification questions.

## M14 — Final submission exports

Excel/DOCX/PDF outputs with evidence references and human approval.
