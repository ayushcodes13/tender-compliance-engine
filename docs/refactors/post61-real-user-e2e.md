# Real user end-to-end hardening

## Confirmed blocker

OEM upload enqueues an `OemDocumentVersion.id`, but the worker currently resolves only tender `DocumentVersion` IDs. A normal OEM upload therefore cannot become `OemTextSegment` evidence and breaks the actual user journey.

## Scope

- teach the existing worker to recognize and process OEM document-version jobs;
- parse immutable OEM bytes through the same parser adapter;
- persist searchable OEM text segments idempotently;
- mark OEM processing status truthfully on success/partial/failure;
- add a real integration test beginning at HTTP project creation + tender upload, exercising the worker rather than pre-seeding document rows;
- add the analogous OEM upload → worker → searchable segment proof;
- then continue through evidence proposal/review and final output wherever deterministic fixtures make that reliable;
- keep the worker simple: OEM processing does not pretend to have tender requirement-extraction stages.

## Exit criteria

A normal supported user path can upload both source types and reach searchable tender/OEM state without manual database inserts for those ingestion steps.
