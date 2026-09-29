# Architecture

## Architecture goals

- Evidence-first and auditable.
- Simple enough for an MVP.
- Provider-agnostic seams around OCR, LLM, storage, and async execution.
- Phase 2 can be added without replacing the core document/requirement model.

## System view

```text
┌──────────────────────┐
│     Next.js Web      │
│ project / upload /   │
│ review / matrix      │
└──────────┬───────────┘
           │ HTTPS / JSON
           ▼
┌──────────────────────┐
│      FastAPI API     │
│ auth / projects /    │
│ docs / requirements  │
└──────┬───────┬───────┘
       │       │ enqueue
       │       ▼
       │  ┌──────────────────┐
       │  │ Background worker │
       │  │ parse/OCR/extract │
       │  └──────┬───────────┘
       │         │
       ▼         ▼
┌────────────┐  ┌──────────────────┐
│ PostgreSQL │  │ S3/Object storage │
│ metadata & │  │ originals/pages   │
│ audit data │  │ rendered assets   │
└────────────┘  └──────────────────┘
       ▲
       │
┌──────┴───────────────────────────┐
│ Adapters                         │
│ parser | OCR | LLM | export      │
└──────────────────────────────────┘
```

Redis is included locally as the queue/broker seam. Phase 1 should not introduce a complex distributed-processing topology until document throughput actually requires it.

## Backend layers

### API layer

Transport concerns only:

- request validation
- authentication/authorization
- response serialization
- job submission
- pagination/filtering

### Application services

Own use-case orchestration:

- create project
- ingest document
- process document version
- create/reconcile extracted requirements
- review/split/merge requirement
- produce export

### Domain layer

Core concepts:

- project
- document/version/page
- requirement/category/source
- review state
- audit event

Later:

- OEM document/evidence
- compliance assessment
- deviation
- clarification request

### Adapters

External provider integrations are isolated behind interfaces:

- object storage
- parser
- OCR
- LLM structured extraction
- async job runner
- spreadsheet export

This prevents the product from becoming coupled to one vendor.

## Document-processing flow

```text
Upload
  ↓
File validation
  ↓
Immutable object storage
  ↓
DocumentVersion row
  ↓
Page enumeration/rendering
  ↓
Text extraction or OCR per page
  ↓
Header/footer cleanup + structure preservation
  ↓
Requirement candidate extraction
  ↓
Structured validation
  ↓
Requirement + RequirementSource persistence
  ↓
Human review
```

## LLM responsibility in Phase 1

LLM may help with:

- deciding which source text constitutes a technical requirement
- splitting independent requirements
- grouping connected multi-sentence requirements
- generating conservative normalized wording
- extracting structured constraints when unambiguous

LLM must not:

- invent missing document text
- guess page/clause metadata
- silently repair uncertain OCR
- assess vendor compliance

LLM output is schema-validated before persistence.

## Deterministic responsibility

Even in Phase 1 deterministic code should own:

- IDs
- document/page ordering
- file hashes/versioning
- source offsets/coordinates
- state transitions
- merge/split lineage
- export generation
- audit events

Phase 2 extends deterministic logic to numerical/unit comparisons.

## Phase 2 seams

The following concepts are designed but not implemented yet:

- OEM document/version
- evidence/evidence location
- vendor specification
- compliance assessment
- contradiction
- deviation
- clarification request
- semantic retrieval index

The Phase 1 document/location model should be reusable for OEM material.

## API direction

Initial groups:

```text
/health
/projects
/projects/{project_id}/documents
/documents/{document_id}/versions
/document-versions/{version_id}/process
/projects/{project_id}/requirements
/requirements/{requirement_id}
/requirements/{requirement_id}/split
/requirements/merge
/projects/{project_id}/exports
```

Do not expose endpoints before their backing behavior exists.

## Observability

At minimum record:

- request/job correlation ID
- project/document/version identifiers
- processing stage and duration
- parser/OCR/LLM provider and model version where relevant
- validation failures
- retry count
- requirement count per processing run
- manual review actions

Avoid logging confidential full-document bodies by default.
