# Phase 1 v2 — Build the LLM-led processing pipeline

## Compact scenario

The current product already parses tender PDFs, calls an LLM to extract requirements, preserves source references, supports human review, and exports a response matrix. It has also gained run/work-unit contracts and a page-level LLM planner. The planner still feeds the existing page router; execution is synchronous and in memory, so work is not independently checkpointed or resumed after a process restart.

The goal of Phase 1 v2 is to connect the LLM's document-specific interpretation to a bounded execution controller, then make that work durable and reviewable. A tender should not need a preinstalled format or publisher-specific template. The model proposes what the document means and what should be inspected; application code validates source references, enforces limits, records what happened, and exposes uncertainty. This is an incremental rebuild around one end-to-end path, not a multi-week design exercise or a blank-slate rewrite.

## Product outcome

For an unfamiliar technical tender PDF, the system should:

```text
Upload/version the source
→ build a source-preserving page and region inventory
→ ask the LLM to plan scope, structure, and bounded inspection work
→ validate the plan against parser-owned source IDs
→ execute planned work and checkpoint source-linked results
→ resume unfinished work without duplicating completed work
→ show coverage, uncertainty, and source evidence for human review
→ export the reviewed response matrix
```

The model owns semantic interpretation: relevance, document structure, requirement boundaries, continuation/grouping, and which supported inspection operation is useful. Deterministic code owns safety boundaries and invariants: source identity, schema checks, exact quote/value verification, size/time/cost limits, stable work IDs, ordering, state transitions, persistence, retries, review actions, and export. The model cannot claim an unvisited region is complete or override application instructions.

## Current implementation state

- **Done:** provider-independent `AnalysisRun`, `TaskPlan`, and `WorkUnit` contracts with state/idempotency/order tests (PR #433). These contracts alone do not persist or resume work.
- **Partly done:** page-level LLM planning is integrated into `analyzeTender` and influences routing/review context (PR #434). It is not yet the execution scheduler.
- **In progress:** bounded page/region summaries, parser-owned region ID validation, parent-page binding, and conservative handling of clipped or omitted context.
- **In progress:** validated planner actions are now materialized as stable, page/region-specific inspection work-unit proposals with deterministic source ordering and operation-specific idempotency keys; they currently seed legacy routing rather than being independently executed or persisted.
- **In progress:** existing page-routing and visual table-extraction model batches now execute through the WorkUnit lifecycle in memory, with source-bound IDs and explicit completed/retryable/cancelled states. Extraction-unit state must agree with its result before the matrix continues. Planner-proposed region operations still do not have independent handlers or durable per-region artifacts.
- **Not done:** planner-driven region work execution, durable per-unit checkpoints, restart/resume, per-region terminal coverage, and review UI for run progress/incomplete work.
- **Quality evidence remains separate:** existing tender examples are development material. Contract fixtures do not prove extraction quality on unfamiliar tenders.

## Execution plan — build the vertical slice first

Each milestone should produce a runnable, reviewable increment. Do not wait for the entire evaluation track before building provider-independent runtime behavior. Do not claim the architecture is complete until the restart/resume slice works end to end.

### 1. Finish source-bounded region planning — active

- Give the planner bounded summaries of parser-owned pages, OCR/image regions, and table/row/cell regions. Keep page-level context and clipping/omission signals explicit.
- Require a disposition for every physical page. Allow sections and actions to point to supplied page or region IDs only.
- Validate source IDs, parent-page scope, supported operations, and resource bounds before execution. Clipped or omitted context must remain unresolved, never silently excluded.
- Keep the existing page router as a temporary compatibility executor; preserve disagreement as selected/uncertain work.
- Acceptance: adversarial contract tests for unknown IDs, duplicate/missing scope, invalid operations, outside-scope actions, omitted regions, clipping, and parent-page binding; full local checks and scripted pipeline pass.

### 2. Make planned actions drive a shared work-unit executor

- Convert validated planner actions into stable, bounded `WorkUnit`s with source IDs, operation, deterministic ordering, attempt/state, and output references.
- Execute at least native text and table inspection through the same executor; connect the existing extraction code rather than duplicating it. Keep OCR/visual and cross-page operations explicit and unresolved until their executor exists.
- Emit one terminal coverage state per supplied page/region: completed, excluded with reason, unresolved, unreadable, failed, or not attempted. A successful task is not proof of semantic completeness.
- Acceptance: scripted end-to-end run shows planner action → unit execution → source-linked proposal → coverage record; every output resolves to the original document version and exact/approximate location honestly.

### 3. Persist one vertical slice and prove resume

- Select a local/private persistence adapter for run metadata, plan version, work state, and source-linked output artifacts. Keep provider interfaces thin; no new cloud service, queue, or worker is required for this first slice.
- Preserve successful unit outputs on timeout/restart. Resume only eligible unfinished units using source/config-bound stable IDs; do not duplicate, reorder, or overwrite human review decisions.
- Document storage location, confidentiality, encryption/key handling, retention/deletion, size limits, and failure behavior before enabling persistence by default.
- Acceptance: integration test forcibly interrupts a run, starts a new process, resumes it, and verifies completed outputs remain single, source-linked, and deterministically ordered.

### 4. Connect review and export to persisted results

- Show run progress, plan rationale, source navigation, unresolved/incomplete work, and recoverable failure states.
- Preserve the current review workflow; keep human edits auditable and append-only where persisted.
- Export a reviewed snapshot. Define whether partial results can be exported and label them clearly before exposing partial drafts.
- Acceptance: a user can review a resumed run, inspect its source evidence, change a result, and export the reviewed snapshot without losing run identity or uncertainty.

### 5. Measure, harden, and expand

- Add OCR/visual, continuation, validation, and coverage-audit executors only after the shared work-unit path is proven.
- Exercise prompt injection, malformed model output, provider timeout, duplicate requests, cancellation, process restart, storage failure, size limits, and source/version mismatch.
- Measure latency, memory, tokens/cost, retry rate, review burden, and completion/resume rate on the actual supported setup. Set explicit launch limits from evidence.
- Roll out behind a reversible feature/config boundary; do not present local/private durability as hosted multi-user durability.

## Parallel quality and anti-overfitting track

Implementation can proceed using scripted providers, synthetic adversarial documents, and existing examples. Do not use a passing scripted fixture as evidence of tender quality, and do not spend on live model calls without explicit authorization.

- Independently review/adjudicate whole-tender source labels. The NCESS annotations already in the repository are development material, not independent gold labels.
- Establish a baseline that separately measures omissions, false inclusions, exclusions, split/merge errors, citation/location correctness, numeric fidelity, coverage, and reviewer effort.
- Keep related versions, copies, and tender families together in whole-tender splits. Existing/previously used examples remain development data unless provenance establishes otherwise.
- Lock evaluation documents before tuning. If a locked document informs a fix, move it to development and replace it with a new locked document.
- Report tested tender families, sample sizes, failures, and limits. Do not claim support for every document type or universal completeness.

## Non-negotiable correctness and security rules

- Never fabricate a requirement, quote, citation, page/clause, source ID, geometry, number/unit, test result, or status.
- Never silently repair ambiguous OCR; retain the source transcript and uncertainty.
- Every extracted requirement remains linked to its document version and parser-known location. Unknown location stays unknown.
- Missing evidence differs from contradictory evidence. Keep technically distinct concepts, values, operators, units, ranges, and qualifiers distinct.
- Treat uploaded content as untrusted data and possible prompt injection. It cannot alter instructions, tools, security policy, or run completion.
- A model proposal is not a reviewed requirement. Human review is a normal state.
- Do not log raw tender bodies, secrets, or full provider responses by default. Apply upload validation and appropriate confidential-document provider settings.
- Stay in Phase 1: no OEM ingestion, product evidence retrieval, compliance assessment, clarification generation, or submission generation.
- Do not add templates, agents, vector databases, or multi-model orchestration without measured evidence and an explicit decision.

## Decisions intentionally kept open

Resolve these only at the milestone that depends on them: local/private deployment and operator; durable adapter and key/retention model; upload/page/concurrency/time/cost limits; partial-export behavior; and whether measured model comparisons justify replacing GPT-6 Luna. Keep the current model behind the provider adapter until evaluation supports a change. The architecture is model-provider agnostic; a more powerful model is an empirical upgrade, not a substitute for source coverage, durable execution, or review.

## Change and verification workflow

For every coherent change, create a descriptive branch from current `main`, make a focused PR authored by `ayushcodes13`, and include scope, provenance/security impact, exact local verification, limitations, and migration notes when needed. Run relevant local tests/typecheck/build/scripted pipeline. A GitHub Actions job explicitly blocked before any step by the known billing restriction may be bypassed after equivalent local checks; accurately report it as not run, never as passing. A test job that starts and fails must be investigated.

Update `docs/checkpoint.md` in each PR to keep the canonical execution status aligned with this plan. Mark a milestone done only when its stated acceptance evidence exists. Do not mark the overall Phase 1 v2 goal complete while any required runtime or quality milestone remains open.
