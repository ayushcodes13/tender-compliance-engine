# Data Model

The schema is designed so Phase 1 can ship without pretending that Phase 2 exists, while still avoiding a future rewrite of provenance and document versioning.

## Core Phase 1 entities

### User

Identity controlled by the authentication provider. Store only product-relevant profile/authorization metadata.

### Organization

Tenant boundary for projects and documents.

Important fields:

- `id` UUID
- `name`
- `created_at`, `updated_at`

### Project

Represents one tender-response workspace.

Important fields:

- `id` UUID
- `organization_id`
- `name`
- `external_tender_id` nullable
- `status`
- `created_by`
- timestamps

### TenderDocument

Logical tender document. Versions are separate.

Fields:

- `id`
- `project_id`
- `display_name`
- `document_type`
- timestamps

### DocumentVersion

Immutable uploaded version.

Fields:

- `id`
- `document_id`
- `version_number`
- `object_key`
- `sha256`
- `mime_type`
- `size_bytes`
- `processing_status`
- `parser_name/version`
- `ocr_name/version` when used
- timestamps

Constraint: `(document_id, version_number)` unique.

### DocumentPage

Page-level source representation.

Fields:

- `id`
- `document_version_id`
- `page_number`
- `extracted_text`
- `ocr_used`
- `ocr_confidence` nullable
- `rendered_image_object_key` nullable
- structural metadata JSONB where unavoidable

Constraint: `(document_version_id, page_number)` unique.

### RequirementCategory

Project/organization taxonomy.

Fields:

- `id`
- `organization_id`
- `name`
- `parent_id` nullable

### Requirement

Human-reviewable normalized technical requirement.

Fields:

- `id`
- `project_id`
- `parent_requirement_id` nullable
- `category_id` nullable
- `raw_text`
- `normalized_text`
- `mandatory` nullable/tri-state rather than guessed false
- `review_status`
- `sort_order`
- `user_notes` nullable
- `created_by_type` (`SYSTEM`, `USER`)
- `created_at`, `updated_at`
- `superseded_at` nullable

Do not overload this row with source coordinates; a requirement may have multiple source fragments.

### RequirementSource

Links a requirement to exact tender provenance.

Fields:

- `id`
- `requirement_id`
- `document_version_id`
- `page_id`
- `clause_number` nullable
- `section_label` nullable
- `source_text`
- `text_start` nullable
- `text_end` nullable
- `bounding_box` nullable JSONB
- `location_precision` (`EXACT`, `APPROXIMATE`)
- `ocr_confidence` nullable
- timestamps

A source location that is not known must remain null rather than fabricated.

### RequirementConstraint

Structured normalized constraint for deterministic downstream use.

Fields:

- `id`
- `requirement_id`
- `parameter_name`
- `operator` nullable
- `value_numeric` nullable
- `lower_bound` nullable
- `upper_bound` nullable
- `unit` nullable
- `tolerance` nullable
- `qualitative_condition` nullable
- `normalization_status`
- `raw_fragment`

### RequirementRevision

Immutable record of material user/system edits.

Fields:

- `id`
- `requirement_id`
- `revision_number`
- snapshot/diff payload
- `changed_by`
- `change_reason` nullable
- `created_at`

### RequirementRelation

Tracks lineage for split/merge operations.

Fields:

- `id`
- `from_requirement_id`
- `to_requirement_id`
- `relation_type` (`SPLIT_INTO`, `MERGED_INTO`, `SUPERSEDES`)
- `created_at`

### AuditLog

Cross-cutting audit event.

Fields:

- `id`
- `organization_id`
- `project_id` nullable
- `actor_type`
- `actor_id` nullable
- `action`
- `entity_type`
- `entity_id`
- minimal structured metadata
- `created_at`

## Phase 2 entities reserved conceptually

Do not create empty tables until implementation begins unless a migration dependency requires them.

- `OEMDocument`
- `OEMDocumentVersion`
- `Evidence`
- `EvidenceLocation`
- `VendorSpecification`
- `ComplianceAssessment`
- `Deviation`
- `ClarificationRequest`

They should reuse the same document/version/page provenance design.

## Indexes

Minimum useful indexes:

- all foreign keys
- `Project(organization_id, status)`
- `DocumentVersion(document_id, version_number)` unique
- `DocumentPage(document_version_id, page_number)` unique
- `Requirement(project_id, review_status, sort_order)`
- `RequirementSource(requirement_id)`
- `RequirementSource(document_version_id, page_id)`
- `AuditLog(project_id, created_at)`

## Avoid redundant storage

Do not duplicate:

- original document bytes in PostgreSQL
- page text on every requirement when a source record can point to it
- computed compliance status in Phase 1
- guessed page/clause metadata
- normalized values that cannot be traced to a source fragment
