# Phase 1 v2 — Build the LLM-led processing pipeline

## Compact scenario

The current product parses tender PDFs, uses an LLM to extract requirements, preserves source references, supports human review, and exports a response matrix. It now also has a page-level LLM planner, typed work units, and an opt-in encrypted local run store wired into analysis. The planner still mostly seeds the existing routing/extraction flow; region actions do not yet independently drive execution. Local runs can checkpoint and resume, while provider calls still execute in the request process rather than through a durable worker.

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
- **Done: resumable local run path:** PR #440 connects the opt-in encrypted SQLite adapter to `analyzeTender`, binds runs to PDF and pipeline-configuration fingerprints, revalidates saved plans, checkpoints routing and visual extraction units, and saves completed analysis before success. A follow-up now checkpoints native-text extraction batches as source-page-bound units with authenticated result artifacts. The browser retains only a fingerprint-to-opaque-run-ID mapping and asks the user to reselect the PDF after reload. The adapter is local/private only and refuses serverless use.
- **Verified synthetically:** unit suite (446), typecheck, production build, and scripted pipeline pass. The scripted pipeline interrupts during four native-text extraction batches, restarts Next.js, reuses the completed batch artifact, reruns only the three unfinished batches, preserves source order, and rejects a different PDF or endpoint configuration before model calls. A separate local browser acceptance used a scripted provider to cancel, reload, resume, review a source-linked requirement, edit the response, and download XLSX/DOCX/PDF. Export contents were independently inspected. This proves the exercised resume/review/export mechanics, not extraction quality or real-tender completeness.
- **First planner-driven operation implemented:** PR #445 adds actual parser-owned native-text block IDs to the planner inventory, validates mode/source compatibility, and executes selected blocks through the existing extraction schema in bounded, stable WorkUnits. Results use the existing encrypted artifact path; candidate quotes are constrained to the selected block and keep its exact parser anchor. Successfully executed blocks are removed from duplicate legacy extraction input, while the independent full-page omission audit still sees the original page. Empty/unsupported/deferred actions remain visible. A scripted provider interruption now proves that a planner-selected unit retries after a Next.js restart, reuses the saved plan and completed routing artifact, preserves its source link, and sends only the still-uncovered block through fallback. The structured-table fast path reports actions as deferred because it does not yet execute them as planner-bound operations.
- **Planner/executor gap remains open:** OCR, image/visual, table-region, and cross-page actions do not yet have planner-bound handlers; source-wide terminal coverage is not established by one native-text action. R2/R3 remain incomplete until supported operations and fallback/unresolved states are consistently executed, persisted, and reviewed across the document paths.
- **Active reliability investigation:** the retained sixth 42-page run log shows five general-extraction responses parsed and the page-17 batch failed after 62.262 seconds with `provider_connection`; no response sheet was returned, and the dev server later logged a compilation/runtime error. The exact reason successful work did not yield a result is not yet proven. The apparent `completedSourceWork` condition is not established as the cause: the five logged responses should make that branch continue. Reproduce the boundary with a deterministic provider and inspect the complete request, stream, and server lifecycle before changing policy.
- **Open:** reliable partial-result/resume behavior under the observed 42-page failure, planner-operation-specific restart fault injection, real-tender quality evaluation on independently adjudicated evidence, and planner-driven execution for every supported region family. Synthetic workflow acceptance is not a broad extraction-quality pass.
- **Quality evidence remains separate:** existing tender examples are development material. Contract fixtures do not prove extraction quality on unfamiliar tenders.

## Product acceptance gates — required alongside the architecture

The architecture work exists to fix the product, not to defer known product failures. After the smallest resumable slice is integrated, return to these acceptance gates before calling Phase 1 usable:

1. **Reproduce and resolve the 42-page failure.** Keep two observations distinct: an earlier run parsed only 4/9 batches before ending without a response sheet; the later retained run parsed five general-extraction responses and had a 62.262-second provider-connection failure on page 17, followed by no response sheet and a dev-server compilation/runtime error. The later log does not yet prove why earlier work did not yield a result. Replay the failure boundary with a deterministic provider and inspect batch accumulation, provider error propagation, checkpoint writes, SSE terminal state, and dev-server health. Fix the demonstrated general cause; do not add a tender-specific classifier or merely raise the timeout.
2. **Run controlled live evaluations within the approved cap.** The referenced sprint brief authorizes up to six paid live analyses and $30 cumulative additional inference spend. Track provider/model, token usage, estimated/billed cost, document family, commit, duration, and outcome. Stop before either cap. Use existing `examples/` as development material; do not describe it as held-out evaluation.
3. **Complete the operator workflow in a real browser.** Verify upload, progress, completed result, source navigation and exact/approximate highlighting, correction/addition/removal/review, encrypted save/resume after reload, and DOCX/XLSX/PDF output. Open generated files independently and inspect text, citations, edits, deleted rows, numbers/units, special characters, and layout. Unit tests alone do not pass this gate.
4. **Verify a free private deployment or document why local is required.** Check current hosting limits, target architecture/native dependencies, authentication, credentials, request memory/time, and ingress with a synthetic 32 MiB PDF. Upload acceptance is not successful processing. Do not expose a public unauthenticated app or upgrade to paid hosting. Vercel/serverless must not use the local SQLite adapter as durable storage.

Report each gate independently as passed, failed, blocked, or not run. A successful build or scripted provider fixture is not an end-to-end acceptance result.

## Execution plan — prove the working path before expanding it

Architecture agreement is complete enough to build. Do not schedule another architecture-redesign phase. The agreed design is an LLM-directed, application-controlled pipeline: the LLM interprets each tender's structure and proposes what to inspect; the application binds proposals to parser-owned sources, runs bounded supported handlers, verifies evidence, persists outcomes, and keeps unresolved work visible. There is no publisher-template catalog and no claim that an LLM alone can guarantee correctness.

Build and integrate a working vertical slice now, then expand the operation handlers. Do not spend weeks redesigning before shipping. Keep each milestone runnable and reviewable; use local deterministic/scripted providers for fault injection and reserve paid live evaluation for the explicitly authorized cap. Existing examples are development material, not independent held-out evidence.

### 1. Resumable local run path — complete

- Connect the encrypted local SQLite adapter to `analyzeTender`: persist a source/config-bound run, the validated task plan, work-unit state and completed outputs; save the final result before reporting success.
- Resume only when the reselected PDF fingerprint and pipeline/model configuration match. Revalidate a saved plan against the current parser inventory. Reuse only completed units with authenticated result artifacts; return running units to retryable and rerun them. Keep source verification and downstream validation in the resume path.
- Propagate the opaque run ID in progress and let the browser remember only that ID keyed by the exact PDF SHA-256. Never store tender text or model output in browser local storage. Require the user to reselect the PDF after reload.
- Keep the store opt-in, encrypted, local/private and unavailable on ephemeral serverless filesystems. Document key handling, location, deletion, size and failure behavior. A persistence error must not be presented as a resumable run.
- Acceptance passed: the encrypted store persists a validated plan, page routing, visual extraction, native-text extraction results, and final output; the scripted pipeline interrupts during extraction, restarts the process, reuses the completed artifact, reruns only unfinished units, and retains deterministic requirement order. Wrong-PDF and changed-endpoint resumes are rejected before provider calls. The local browser also completed cancel/reload/resume through review and export.
- Limits: this proves local adapter behavior and the exercised synthetic paths. It does not provide hosted durability, broad failure-mode coverage, or real-tender quality evidence.

### 2. First planner-driven source execution — active implementation task

Make the planner select actual parser-owned content for a real handler. Start with `native_text` text blocks because they have stable IDs, exact page offsets, and an existing extraction/source-verification path; this is the first vertical slice, not a fixed format for tenders. The model still decides which supported content and structure matter for each tender.

- Include bounded, explicitly clipped native text-block candidates in the planner inventory. Bind every candidate to its parser ID, owning page, text, and known offsets. Validate that each proposed operation is compatible with the source kind; reject forged, ambiguous, duplicate, or incompatible references.
- Materialize stable, bounded work units from validated `native_text` actions and preserve their action/source relationships. The handler may send only selected block text, in source order, under the existing extraction schema. Returned quotes must pass the existing literal source/page checks; do not concatenate non-contiguous blocks into fabricated continuous evidence.
- Persist accepted results as authenticated artifacts and reconstruct ephemeral trace IDs when resuming. Reuse completed units only when source, configuration, and artifact validation match. Retry unfinished work without duplicating accepted results.
- Track handled, incomplete, unsupported, and fallback source coverage. Do not call unsupported OCR, visual, table, or cross-page actions complete. Use the legacy path only for uncovered content where safe, and record that fallback so coverage cannot be overstated. Avoid duplicate extraction for source blocks already successfully handled by the planner.
- Preserve prompt-injection boundaries, page/source identity, clipping and omission signals, ordering, cancellation, retries, request budgets, and the current human-review/export contract.
- Acceptance: scripted tests prove real planner input includes parser text-block IDs; wrong source kinds are rejected; only selected content reaches the handler; grounded outputs keep page/source links; completed units survive restart; remaining units retry; overlapping/unsupported/uncovered work stays explicit; the integrated result can be reviewed and exported without claiming unvisited content is complete.

Keep vector-table extraction's current header-continuation behavior intact until it can be wrapped in its own source-bound handler and coverage contract. Add OCR, visual, table, and cross-page handlers incrementally based on inventory needs, with the same action → validated source → bounded WorkUnit → persisted result → coverage contract. Never represent an unimplemented mode as completed work.

### 3. Reproduce and fix the 42-page failure

- Start with both retained observations in `.local/client-review/current-main-audit-2026-11-09.json` and `.local/client-review/42page-throughput-four-2026-11-09.log`. The later log has five parsed general-extraction responses plus a page-17 provider connection failure; its final analysis error and subsequent dev-server error need separate causal attribution.
- Use durable checkpoints to isolate the failing stage. A deterministic six-batch regression now covers five accepted responses followed by a provider connection failure and confirms partial results plus explicit page incompleteness. Opt-in telemetry now distinguishes parseable JSON from schema-valid extraction responses. Compare the historical live-run evidence against these signals; inspect checkpoint writes, terminal SSE behavior, and dev-server compilation/runtime state before changing failure policy.
- Fix the general cause; do not add a tender-specific classifier or merely raise a timeout. Any partial result must retain explicit incomplete coverage and must not be exported as complete.
- Acceptance: repeatable reproduction or trace replay identifies the failure; a corrected run completes or ends in an honest resumable/incomplete state; report latency, batches, retries, coverage, model/tokens and cost. A single run is not a quality score.

### 4. Complete browser review and export acceptance

- The synthetic-provider browser path has already exercised cancel/reload/resume, source navigation, one review/edit, and XLSX/DOCX/PDF exports. Extend it against the planner-driven path and cover fresh plus resumed runs, exact and approximate citations, add/remove/review actions, visible incomplete states, and export from the reviewed snapshot.
- Open generated files independently and inspect wording, citations, edits/deletions, numbers/units, special characters, and layout. Ensure interrupted or incomplete work cannot masquerade as a complete matrix.
- Acceptance: retain repeatable browser steps and artifacts for the integrated path. Synthetic browser evidence proves workflow mechanics only; it does not prove real-tender extraction quality.

### 5. Broaden evidence and operational hardening

- Run controlled live evaluations within the approved maximum of six analyses and $30 cumulative additional inference spend. Track provider/model, token usage, estimated cost, document family, commit, duration, retries, and outcome; stop at either cap.
- Use existing `examples/` as development material, not held-out evaluation. Keep related tenders together in whole-tender splits; independently adjudicate labels; report omissions, false inclusions, exclusions, split/merge errors, citation/location correctness, numeric fidelity, coverage, and reviewer effort with sample sizes and limitations.
- Verify the current free/private deployment and synthetic 32 MiB ingress only after checking authentication, secrets, memory/time, native dependencies, and storage constraints. Do not create paid infrastructure or expose an unauthenticated service.
- Acceptance: report each quality, deployment, security, and cost gate separately as passed, failed, blocked, or not run. No universal-document claim without independent evidence.

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
