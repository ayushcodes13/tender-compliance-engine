# Phase 1 Product Requirements Document

## Objective

Reduce the manual work required to turn technical tender documents into a clean, auditable compliance matrix while preserving the exact provenance of each extracted requirement.

Phase 1 does **not** decide whether an OEM or vendor complies with the tender.

## Target users

- scientific-instrument distributors
- industrial equipment suppliers
- semiconductor equipment companies
- defence suppliers
- laboratory-equipment companies
- engineering/system-integrator teams
- technical sales and tender teams

## Primary user journey

1. User opens the application.
2. User creates a tender project.
3. User uploads one or more tender documents.
4. System stores an immutable document version.
5. System parses digitally generated pages and routes scanned pages to OCR.
6. System creates a source-preserving page representation.
7. System extracts explicit technical requirements.
8. User reviews extracted requirements.
9. User may edit wording, split/merge, categorize, reorder, mark mandatory when supported, or add notes.
10. Every requirement retains source document/page/clause/location information.
11. System generates a structured compliance matrix.
12. User exports the reviewed matrix to Excel.

## Functional requirements

### Projects

- Create, view, rename, archive, and reopen a tender project.
- Project has a stable identifier and audit timestamps.
- Project state reflects whether documents are uploaded, processing is underway, review is required, or export is ready.

### Documents

- Accept PDF first; DOCX is supported by the architecture and may land after the first PDF milestone.
- Preserve the original upload.
- Create explicit document versions instead of overwriting prior source material.
- Record parse/OCR status and failures.
- Preserve page ordering and page-level text/image metadata.

### Requirement extraction

For each extracted requirement preserve at minimum:

- stable requirement ID
- raw text
- normalized text
- category/subcategory when known
- mandatory flag only when supported
- clause/section label when known
- page number when known
- source document/version
- parent requirement when applicable
- units
- structured numerical constraints when safely extractable
- exact source text
- OCR warning
- extraction confidence/uncertainty metadata

The system must support:

- multiple independent requirements in one sentence
- one requirement spanning multiple sentences
- tables
- numbered/nested clauses
- multi-page requirements
- repeated headers/footers
- OCR corruption
- duplicate requirements

### Review

Reviewer can:

- edit normalized wording
- split a requirement
- merge requirements
- delete a mistaken extraction
- reorder rows
- categorize
- mark mandatory when the source supports it
- add notes
- open the cited source

Every manual mutation creates an audit record.

### Compliance matrix

Minimum columns:

| Column | Purpose |
|---|---|
| S.No. | Human-readable ordering |
| Requirement ID | Stable internal/external reference |
| Tender Requirement | Reviewed requirement text |
| Category | User/system category |
| Clause | Source clause/section |
| Source Page | Source page |
| Mandatory | Whether explicitly mandatory |
| User Notes | Reviewer notes |
| Review Status | Review workflow state |

Allowed Phase 1 review states:

- `UNREVIEWED`
- `REVIEWED`
- `NEEDS_CLARIFICATION`
- `OCR_WARNING`

### Export

- Export reviewed matrix to XLSX.
- Include project/tender identifier and generation timestamp.
- Preserve ordering and source references.
- Do not add vendor-compliance columns until Phase 2.

## Non-functional requirements

- Organization/project authorization boundaries.
- Source traceability survives processing and manual edits.
- Idempotent/background-safe processing jobs.
- Retryable document processing without duplicate requirements.
- Clear error states instead of silent partial success.
- Auditable user and AI/system actions.
- Confidential document handling.
- Deterministic serialization for exports where practical.

## Failure states

- unsupported file
- password-protected/unreadable PDF
- malware/file validation failure
- parser failure
- OCR failure
- partial page extraction
- ambiguous OCR
- LLM extraction failure
- invalid structured LLM output
- requirement without a trustworthy source anchor
- export failure

Failures must not be converted into fabricated content.

## Acceptance criteria for Phase 1

A user can create a project, upload a tender, process it, review and edit extracted requirements with intact source references, and export the reviewed compliance matrix to Excel. Uncertain extraction is visible and reviewable. No part of the workflow claims OEM/vendor compliance.
