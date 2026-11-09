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

- **Existing product integration:** PRs #411, #412, #414, #415, #416, and #417 are merged. PR #413 was closed in favor of #415's encrypted portable review session. This integration work is complete; do not reopen it without new evidence.
- **Done:** provider-independent `AnalysisRun`, `TaskPlan`, and `WorkUnit` contracts with state/idempotency/order tests (PR #433). These contracts alone do not persist or resume work.
- **Partly done:** page-level LLM planning is integrated into `analyzeTender` and influences routing/review context (PR #434). It is not yet the execution scheduler.
- **In progress:** bounded page/region summaries, parser-owned region ID validation, parent-page binding, and conservative handling of clipped or omitted context.
- **In progress:** validated planner actions are now materialized as stable, page/region-specific inspection work-unit proposals with deterministic source ordering and operation-specific idempotency keys; they currently seed legacy routing rather than being independently executed or persisted.
- **In progress:** existing page-routing and visual table-extraction model batches now execute through the WorkUnit lifecycle in memory, with source-bound IDs and explicit completed/retryable/cancelled states. Extraction-unit state must agree with its result before the matrix continues. Planner-proposed region operations still do not have independent handlers or durable per-region artifacts.
- **In progress:** the current branch connects the encrypted SQLite adapter to analysis runs, revalidates saved plans against the reconstructed parser inventory, checkpoints page-routing and visual-extraction batches, and stores completed analysis output before returning it. The browser stores only a PDF-fingerprint-keyed opaque run handle. A scripted-provider integration test interrupts after routing, restarts the Next.js process, and proves the plan/routing outputs are reused. Real-browser reload/resume and mismatch rejection still need proof. The store remains local/private, opt-in, and unavailable as durable storage on Vercel/serverless.
- **Not done:** fault-injected end-to-end resume proof, recoverable UI status after reload, the 42-page failure diagnosis/fix, full review/export acceptance on a resumed run, planner-driven independent region handlers, and per-region terminal coverage.
- **Quality evidence remains separate:** existing tender examples are development material. Contract fixtures do not prove extraction quality on unfamiliar tenders.

## Product acceptance gates — required alongside the architecture

The architecture work exists to fix the product, not to defer known product failures. After the smallest resumable slice is integrated, return to these acceptance gates before calling Phase 1 usable:

1. **Reproduce and resolve the 42-page failure.** The recorded run read all 42 pages and completed 5/5 routing groups and 13/13 header mappings, but only 4/9 technical extraction batches parsed; the stream ended without a usable response sheet after 290.02 seconds. Start with saved traces and provider/model timing. Inspect batch sizing, output/schema failures, timeouts, retry behavior, SSE terminal state, concurrency, and partial-result handling. Fix the demonstrated general cause; do not add a tender-specific classifier or merely raise the timeout.
2. **Run controlled live evaluations within the approved cap.** The referenced sprint brief authorizes up to six paid live analyses and $30 cumulative additional inference spend. Track provider/model, token usage, estimated/billed cost, document family, commit, duration, and outcome. Stop before either cap. Use existing `examples/` as development material; do not describe it as held-out evaluation.
3. **Complete the operator workflow in a real browser.** Verify upload, progress, completed result, source navigation and exact/approximate highlighting, correction/addition/removal/review, encrypted save/resume after reload, and DOCX/XLSX/PDF output. Open generated files independently and inspect text, citations, edits, deleted rows, numbers/units, special characters, and layout. Unit tests alone do not pass this gate.
4. **Verify a free private deployment or document why local is required.** Check current hosting limits, target architecture/native dependencies, authentication, credentials, request memory/time, and ingress with a synthetic 32 MiB PDF. Upload acceptance is not successful processing. Do not expose a public unauthenticated app or upgrade to paid hosting. Vercel/serverless must not use the local SQLite adapter as durable storage.

Report each gate independently as passed, failed, blocked, or not run. A successful build or scripted provider fixture is not an end-to-end acceptance result.

## Execution plan — prove the working path before expanding it

Architecture agreement is complete enough to build. Do not schedule a separate architecture-redesign phase or block the first end-to-end proof on advanced region scheduling. Each step must yield a runnable increment. The LLM adapts semantic interpretation to the tender; application code enforces source identity, exact evidence, bounded execution, durable state, and honest uncertainty.

### 1. Finish the resumable run path — active

- Connect the encrypted local SQLite adapter to `analyzeTender`: persist a source/config-bound run, the validated task plan, work-unit state and completed outputs; save the final result before reporting success.
- Resume only when the reselected PDF fingerprint and pipeline/model configuration match. Revalidate a saved plan against the current parser inventory. Reuse only completed units with authenticated result artifacts; return running units to retryable and rerun them. Keep source verification and downstream validation in the resume path.
- Propagate the opaque run ID in progress and let the browser remember only that ID keyed by the exact PDF SHA-256. Never store tender text or model output in browser local storage. Require the user to reselect the PDF after reload.
- Keep the store opt-in, encrypted, local/private and unavailable on ephemeral serverless filesystems. Document key handling, location, deletion, size and failure behavior. A persistence error must not be presented as a resumable run.
- Acceptance: fault-injected interruption, fresh process, same PDF/config, exactly-once reuse of completed artifacts, retry of unfinished work, wrong-source/config rejection, and a real browser reload/resume through review.

### 2. Reproduce and fix the 42-page failure through that path

- Start with the saved trace and provider/model timings for the 42-page run: 5/5 routing groups and 13/13 header mappings completed, but only 4/9 extraction batches parsed before 290.02 seconds and no response sheet was returned.
- Use durable checkpoints to isolate the failing stage and preserve successful batches. Inspect batch sizing, malformed/schema output, provider timeouts, retry behavior, concurrency, terminal SSE state and partial-result handling.
- Fix the general cause; do not add a tender-specific classifier or merely raise a timeout. Any partial result must retain explicit incomplete coverage and must not be exported as complete.
- Acceptance: repeatable reproduction or trace replay identifies the failure; a corrected run completes or ends in an honest resumable/incomplete state; report latency, batches, retries, coverage, model/tokens and cost. A single run is not a quality score.

### 3. Complete browser review and export acceptance

- Verify upload, live progress, completed result, source navigation and exact/approximate highlighting, correction/addition/removal/review, encrypted save/resume after reload, and DOCX/XLSX/PDF output.
- Open generated files independently and inspect wording, citations, edits/deletions, numbers/units, special characters, and layout. Ensure an interrupted or incomplete run is visible as such and cannot masquerade as a complete matrix.
- Acceptance: record browser steps and artifacts for a fresh run and a resumed run; test exports from the reviewed snapshot.

### 4. Broaden evidence and operational hardening

- Run controlled live evaluations within the approved maximum of six analyses and $30 cumulative additional inference spend. Track provider/model, token usage, cost, document family, commit, duration, retries and outcome; stop at either cap.
- Use existing `examples/` as development material, not held-out evaluation. Keep related tenders together in whole-tender splits; independently adjudicate labels; report omissions, false inclusions, exclusions, split/merge errors, citation/location correctness, numeric fidelity, coverage, and reviewer effort with sample sizes and limitations.
- Verify the current free/private deployment and synthetic 32 MiB ingress only after checking authentication, secrets, memory/time, native dependencies and storage constraints. Do not create paid infrastructure or expose an unauthenticated service.
- Acceptance: report each quality, deployment, security and cost gate separately as passed, failed, blocked or not run. No universal-document claim without independent evidence.

### 5. Expand planner-driven execution from evidence

- After the resumable path and failure diagnosis, promote validated planner actions from routing hints into independent bounded work units for native text and tables; add OCR/visual and cross-page operations as explicit handlers with per-region coverage.
- Preserve page/region inventory IDs, parent-page binding, clipping/omission signals, deterministic ordering, retries and source verification. Unsupported or unrepresented regions stay unresolved; the model cannot declare unvisited content complete.
- Add operation types only when they close an observed coverage or reliability gap. Keep provider interfaces thin; do not add templates, agents, vector databases, queues or multi-model orchestration without measured need.
- Acceptance: planner action → bounded execution → source-linked result → per-source coverage → resumable review/export, with adversarial tests for forged IDs, prompt injection, malformed output, retries, duplicate requests and incomplete context.

## Parallel quality and anti-overfitting track

Implementation can proceed using scripted providers, synthetic adversarial documents, and existing examples. Do not use a passing scripted fixture as evidence of tender quality. Paid live calls are authorized only under the explicit six-run / $30 cap above; the cap does not authorize paid subscriptions or infrastructure.

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
