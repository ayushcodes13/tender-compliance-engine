# Phase 1 v2 — Build the LLM-led processing pipeline

## Compact scenario

The current product parses tender PDFs, uses an LLM to extract requirements, preserves source references, supports human review, and exports a response matrix. It now also has a page-level LLM planner, typed work units, source-bound native-text/vector-table/OCR/image-region operations, and an opt-in encrypted local run store wired into analysis. Planner execution is still incomplete: table-row/cell, cross-page/continuation, adaptive replanning, and consistent document-wide dispositions remain open. Local runs can checkpoint and resume; provider calls still execute in the request process rather than through a durable worker.

The goal of Phase 1 v2 is to make the LLM the document-specific interpreter and planner, while the application provides a bounded, durable, auditable execution environment. A tender should not need a preinstalled format or publisher-specific template. The model interprets scope, structure, requirement boundaries, continuation, and which supported inspection operations to use. Application code validates source references, runs those operations, verifies evidence, checkpoints progress, and exposes uncertainty. The model can choose among general capabilities; it cannot invent source identity, silently certify unvisited material, or override application policy. This is a focused rebuild of the execution path, not a blank-slate rewrite.

**Agreed implementation rule:** let the LLM decide what the document means and what supported work should happen next; let application code enforce source identity, capability boundaries, evidence checks, budgets, persistence, and truthful review states. Build this as an iterative plan → execute → validate → feed results back loop. Do not add publisher templates or give the model unrestricted execution authority.

## Product outcome

For an unfamiliar technical tender PDF, the system should:

```text
Upload/version the source
→ build a source-preserving page and region inventory
→ ask the LLM to plan scope, structure, and bounded inspection work
→ validate the plan against parser-owned source IDs
→ execute bounded work and checkpoint source-linked results
→ return validated outcomes and unresolved inventory to the LLM for the next decision
→ repeat planning/execution until a defensible stop, review boundary, or budget limit
→ resume unfinished work without duplicating completed work
→ show coverage, uncertainty, and source evidence for human review
→ export the reviewed response matrix
```

The model owns semantic interpretation: relevance, document structure, requirement boundaries, continuation/grouping, and which supported inspection operation is useful. Deterministic code owns safety boundaries and invariants: source identity, schema checks, exact quote/value verification, size/time/cost limits, stable work IDs, ordering, state transitions, persistence, retries, review actions, and export. The model cannot claim an unvisited region is complete or override application instructions.

### Intended planning/execution control loop

The planner is a controller, not a one-shot router. After each bounded work wave, the application returns only validated outcomes, source dispositions, and remaining/failed/ambiguous inventory to the model. The model then proposes the next useful operations, a justified exclusion, a request for clarification, or a stop. The application validates each proposal against parser-owned IDs and supported operation contracts, executes accepted work, and repeats within explicit page, request, time, and cost budgets. This lets the model adapt to document-specific structure and intermediate findings without requiring publisher templates.

An analysis may be called complete only when every inventoried source unit has an explicit disposition and no required work is pending; otherwise it must remain partial or unresolved and visibly require review. A model-declared exclusion is a recorded interpretation, not proof that the source contains no requirement. The operation handlers are reusable capabilities (for example, inspect selected text, OCR transcript, image crop, or table region), while the model chooses which ones apply and how to organize their results. New capability types are added only when the current inventory cannot express a real source type, not as per-tender special cases.

## Current implementation state

- **Existing product integration:** PRs #411, #412, #414, #415, #416, and #417 are merged. PR #413 was closed in favor of #415's encrypted portable review session. This integration work is complete; do not reopen it without new evidence.
- **Done:** provider-independent `AnalysisRun`, `TaskPlan`, and `WorkUnit` contracts with state/idempotency/order tests (PR #433). These contracts alone do not persist or resume work.
- **Partly done:** page-level LLM planning is integrated into `analyzeTender` and influences routing/review context (PR #434). It is not yet the execution scheduler.
- **Contract foundation merged in PR #456:** proposals carry an explicit `continue`, `stop`, or `needs_review` decision; later planner requests can include bounded outcomes; encrypted snapshots retain ordered planning-round records and migrate older one-shot plans into a review-safe round. Repeating an executed source/mode pair is rejected when that outcome is in the current request.
- **Done: resumable local run path:** PR #440 connects the opt-in encrypted SQLite adapter to `analyzeTender`, binds runs to PDF and pipeline-configuration fingerprints, revalidates saved plans, and checkpoints source-bound work. PR #447 closes the provider-failure gap: a partial draft remains paused, retains its opaque run handle, and after restart reuses completed artifacts while retrying only unfinished work. The adapter is local/private only and refuses serverless use. Local unit, typecheck, production build, and scripted restart/retry pipeline checks passed.
- **Verified synthetic baseline through merged PR #449:** planner-selected native-text and vector-table actions, table-handler interruption/restart/retry, completed-artifact reuse, invalid PDF/config resume rejection, general extraction batch recovery, and existing browser review/export mechanics are covered by previously recorded local checks. These prove only exercised workflow mechanics, not extraction quality or real-tender completeness.
- **Planner-driven operations implemented:** PR #445 adds parser-owned native-text block IDs and executes selected blocks through bounded, stable WorkUnits with source-bound quote validation and duplicate-fallback prevention. PR #449 adds selected vector-table classification. PR #450 adds selected OCR-region extraction. Completed results use the encrypted artifact path; unsupported/deferred actions remain visible. Scripted interruption/restart checks prove completed work is reused and unfinished work retried. These are supported operation slices, not broad document-quality evidence.
- **Planner inventory completed in PR #448:** text-heavy pages cannot exhaust the six-region planner budget before parser-owned table, OCR, or image sources are represented. Omitted regions remain explicitly counted and clipped/omitted context cannot be treated as safely excluded. This makes more source types available to the LLM.
- **Done in PR #449: planner-selected vector-table execution.** Planner-selected parser-owned vector table IDs reach the row-classification handler, persist completed classification artifacts, and mark planner coverage executed only after source/table checks succeed. The scripted restart test proves saved-plan reuse and operation retry. This does not execute table-row/cell proposals, non-vector structured layouts without parser table rows, image-only visual or cross-page actions.
- **Done in PR #450: planner-selected OCR execution.** A validated OCR action runs through a bounded extraction WorkUnit, preserves the selected parser OCR region ID and approximate location, keeps the requirement unreviewed, masks successfully executed OCR text from duplicate fallback, and persists a retryable result artifact. The generated scanned-PDF integration forces provider failure, restarts the app, reuses the saved plan, retries exactly once and confirms the source-linked result. Local checks passed: `npm run test:pipeline`, `npm run typecheck`, `npm test` (456 passed), `npm run build`, and `git diff --check`. This proves workflow mechanics only; OCR accuracy and tender completeness remain unmeasured.
- **Done in PRs #453 and #455: image-region execution and truthful operator label.** PR #453 sends only a bounded crop, persists/retries a visual WorkUnit, masks successfully inspected image regions from later page-image fallback, and binds returned text to the parser image ID with approximate location and human-review warning. PR #455 labels VLM transcriptions as visual rather than OCR. Synthetic integration covers failure/restart/retry, crop-only input, identical OCR wording, selected image citation, no fabricated OCR confidence, and unreviewed state. Local build, typecheck, unit tests, full scripted pipeline, and a 2026-11-10 scripted-provider browser run passed for the stated paths. These checks do not measure image transcription quality or tender completeness.
- **Active branch `feat/adaptive-planner-feedback-loop` (not merged):** connects additional planning decisions to native-text extraction, feeds source-validated quote outcomes back to the planner, persists planner decisions as resumable WorkUnits, and retries unfinished work after restart. Later rounds currently support `native_text` only and are limited to three decisions. Scope revisions are not yet applied, adaptive table/OCR/visual/cross-page work is not yet enabled, and document-wide terminal coverage is not established. This is the first executable feedback-loop slice, not the completed architecture.
- **Planner/executor gap remains open:** main has planner-selected native-text, vector-table, OCR, and image-region handlers, but the planner currently decides only the initial wave. Table row/cell actions, cross-page/continuation handling, adaptive use of all supported modes, dynamic scope/disposition updates, consistent document-wide dispositions, and broader review/coverage integration remain open. R2/R3 remain incomplete until supported operations and fallback/unresolved states are consistently executed, persisted, and reviewed across document paths.
- **Verified; partial-run resume fixed in PR #447:** a deterministic six-batch replay proves that five valid extraction batches survive a sixth-batch provider disconnect and are returned with only the failed batch's pages marked incomplete. After restart, the saved run reuses the five completed artifacts, retries only the failed batch, and becomes complete. The retained live log also records a later dev-server error, but does not establish that error as the cause of the earlier live analysis outcome.
- **Done in PR #455:** verified the image-region citation/warning rendering in the browser and corrected the UI to label VLM transcriptions as visual rather than OCR.
- **Open:** merge and verify the bounded adaptive-loop slice; extend later-round planning to supported table/OCR/visual operations; implement table-row/cell and cross-page/continuation actions; apply revised scope/dispositions; complete browser review/export of planner-selected partial/resumed results; and evaluate quality on independently adjudicated evidence. Synthetic workflow acceptance is not a broad extraction-quality pass.
- **Quality evidence remains separate:** existing tender examples are development material. Contract fixtures do not prove extraction quality on unfamiliar tenders.

## Product acceptance gates — required alongside the architecture

The architecture work exists to fix the product, not to defer known product failures. After the smallest resumable slice is integrated, return to these acceptance gates before calling Phase 1 usable:

1. **Reproduce and resolve the 42-page failure.** Keep two observations distinct: an earlier run parsed only 4/9 batches before ending without a response sheet; the later retained run parsed five general-extraction responses and had a 62.262-second provider-connection failure on page 17, followed by no response sheet and a dev-server compilation/runtime error. The later log does not yet prove why earlier work did not yield a result. Replay the failure boundary with a deterministic provider and inspect batch accumulation, provider error propagation, checkpoint writes, SSE terminal state, and dev-server health. Fix the demonstrated general cause; do not add a tender-specific classifier or merely raise the timeout.
2. **Run controlled live evaluations within the approved cap.** The referenced sprint brief authorizes up to six paid live analyses and $30 cumulative additional inference spend. Track provider/model, token usage, estimated/billed cost, document family, commit, duration, and outcome. Stop before either cap. Use existing `examples/` as development material; do not describe it as held-out evaluation.
3. **Complete the operator workflow in a real browser.** Verify upload, progress, completed result, source navigation and exact/approximate highlighting, correction/addition/removal/review, encrypted save/resume after reload, and DOCX/XLSX/PDF output. Open generated files independently and inspect text, citations, edits, deleted rows, numbers/units, special characters, and layout. Unit tests alone do not pass this gate.
4. **Verify a free private deployment or document why local is required.** Check current hosting limits, target architecture/native dependencies, authentication, credentials, request memory/time, and ingress with a synthetic 32 MiB PDF. Upload acceptance is not successful processing. Do not expose a public unauthenticated app or upgrade to paid hosting. Vercel/serverless must not use the local SQLite adapter as durable storage.

Report each gate independently as passed, failed, blocked, or not run. A successful build or scripted provider fixture is not an end-to-end acceptance result.

## Execution plan — implement the adaptive inspection loop

**The architecture decision is complete. Do not spend another phase redesigning it.** Build and evaluate the agreed architecture in short, end-to-end increments. The LLM interprets each tender's structure, proposes and revises work from intermediate outcomes, and decides what to inspect next or when to stop; the application binds proposals to parser-owned sources, runs bounded supported handlers, verifies evidence, persists outcomes, and keeps unresolved work visible. There is no publisher-template catalog. The LLM is responsible for document-specific interpretation, while source identity, auditability, safety limits, and review states remain enforced by the application.

On `main`, the planner runs once before extraction. The active branch adds a bounded follow-up loop for native-text blocks and restart/retry, but it does not yet dynamically revise document scope or choose later table/OCR/visual work. Finish that first vertical slice and then expand the same loop to every supported handler. Do not spend time on another architecture redesign or wait for the broader evaluation program before implementing it.

### Ordered milestones

1. **Complete the bounded native-text feedback loop (active branch).** Keep validated outcomes cumulative across rounds, reject repeated completed source/mode work, persist each decision and execution as resumable units, and prove a forced interruption/restart retries only unfinished work. The current limit is three planner decisions; exceeding it must remain visibly partial.
2. **Apply planning decisions to scope and dispositions.** Reconcile each round against the full parser-owned page/region inventory. Persist explicit relevant, possibly relevant, outside-task, unresolved, executed, failed, and unvisited states with provenance. A model stop or exclusion is never proof of complete coverage; application checks decide whether the run is complete or partial.
3. **Expand the adaptive loop across capabilities.** Allow later rounds to choose existing native-text, vector-table, OCR, and image-crop handlers, then implement table-row/cell and cross-page/continuation operations where current parser inventory and handlers cannot express the source relationship. Every action remains source-bound; unsupported, omitted, clipped, failed, ambiguous, and unvisited regions remain unresolved.
4. **Finish truthful browser review and export.** Exercise fresh, partial, and resumed runs through source navigation, review edits, visible incomplete states, and exports. Open and inspect generated files independently.
5. **Measure quality and operational limits.** Create human-adjudicated whole-tender development/validation/locked-evaluation splits; report omissions, false inclusions, split/merge, citation/location accuracy, numerical fidelity, coverage, uncertainty calibration, latency, cost, and reviewer effort. Existing `examples/` are development material unless provenance supports a clean locked split. Verify private deployment and security limits separately.

### Adaptive-loop acceptance

- A run can contain multiple persisted planner rounds, each tied to a stable input fingerprint and recording the proposal, accepted/rejected actions, and referenced execution outcomes.
- Later round inputs include only validated prior outcomes and an honest remaining/failed/ambiguous inventory; untrusted document content cannot override system policy.
- Every proposed action is checked against current parser-owned IDs, registered handler capability, idempotency, and explicit round/run budgets before it executes.
- A resumed run continues from its latest valid round, reuses authenticated completed artifacts, and does not repeat completed work or lose source order.
- A planner stop alone cannot mark a run complete. Application coverage must show no required or unresolved work; otherwise the result remains partial and reviewable.
- Deterministic tests cover additional work after an initial result, stop, clarification/review request, invalid IDs/unsupported modes, budget exhaustion, provider failure, restart/resume, duplicate prevention, and truthful partial state.
- Scripted end-to-end evidence demonstrates later decisions change from cumulative, source-validated outcomes, including after process restart. This proves control-flow behavior only, not general extraction quality.

**Definition of done:** all supported source types have truthful terminal dispositions; unresolved work cannot be presented as complete; the LLM can adapt the next inspection wave from validated intermediate evidence; runs can resume safely; a human can audit and export the result; and quality/operational claims are backed by independently described evidence. A synthetic fixture proves workflow mechanics, not broad tender quality. Do not claim the system handles every document until evaluation supports that claim.

Build in short, reviewable PRs against this order. Each PR should leave `main` runnable and move a named acceptance item forward. The persisted round/decision contract is already merged in PR #456; the active PR completes the first native-text feedback slice. Follow it by applying dynamic scope/dispositions, enabling later rounds across all existing handlers, adding missing capabilities, and completing operator verification. Use local deterministic/scripted providers for fault injection and reserve paid live evaluation for the explicitly authorized cap. Existing examples are development material, not independent held-out evidence.

### Completed milestone — resumable planner-selected OCR execution (PR #450)

The first execution milestone is complete. Its generated scanned-PDF pipeline proves this chain:

```text
synthetic scanned PDF
→ parser creates an OCR region with a stable source ID
→ LLM planner selects that region by its parser-owned ID
→ bounded OCR extraction runs only on the selected transcript
→ literal quote validation produces an unreviewed, source-linked requirement
→ encrypted run store checkpoints the operation
→ forced provider interruption, process restart, and retry reuse the plan and finish the same operation
→ coverage reports the selected operation accurately
```

The pipeline passed with parser-created OCR source ID, planner selection, bounded transcript-only extraction, literal quote validation, unreviewed source-linked requirement, encrypted checkpoint, forced provider drop, process restart, saved-plan reuse, exactly one retry, and executed coverage after a grounded result. Unit tests, typecheck, production build, and `git diff --check` passed. This synthetic fixture proves mechanics only; it is not evidence of OCR accuracy or tender completeness.

### Completed milestone — review the planner-generated OCR result in the browser

On 2026-11-10, a local Next.js app used a scripted provider and generated scanned PDF. Browser acceptance verified upload, one planner-selected OCR requirement, a visible incomplete-draft warning, the OCR page citation, the approximate source box with the quoted scan line highlighted, explicit “Mark checked”, response editing, Excel export, and encrypted save/reload/restore with the original PDF fingerprint. The downloaded workbook was reopened independently; its requirement, page, checked status and edited remark were present. The restored review retained the same state. The scripted API pipeline separately verifies provider interruption and run resume.

**Limits:** this verifies one synthetic layout and the exercised UI path only. It is not live-model evidence or an OCR accuracy/completeness score. The Phase 1 review page previously showed an OEM compliance panel, contrary to the Phase 1-only scope. This PR removes that panel; the post-change browser check confirms the review, citation, warning, and export controls still work without exposing Phase 2 actions. The UI reload test covered the encrypted human-review file; API interruption/resume was verified separately, not by interrupting a browser session.

### Completed milestone — planner-selected image-region execution (PR #453; browser check pending)

Execute a model-proposed `visual` action against a parser-owned image-region ID using a bounded image crop, then bind any suggested result to that same region and preserve its unverified/approximate evidence state. Persist and retry the operation through the existing WorkUnit path. An unlocalized visual answer must remain review-only and must never be upgraded to a source-grounded requirement by the model's assertion alone.

**Synthetic pass:** a generated image-only PDF proves planner source selection, crop-only provider input, source identity/approximate location, explicit uncertainty, and restart/retry without duplicate work. If the same words also occur in page OCR, the result remains linked to the selected image region and does not inherit OCR confidence or selectable-text offsets.

**Remaining before this milestone is closed:** verify in a real browser that the approximate crop citation and human-review warning render correctly, and that any unresolved page/region keeps the incomplete warning visible. No real tender or live model call is needed for this contract check.

### Follow-on delivery sequence

1. **Completed in PR #452: keep the Phase 1 UI inside Phase 1 scope.** The existing OEM compliance panel is removed from the Phase 1 response sheet; its Phase 2 actions are not exposed in this journey.
2. **Complete planner-directed source operations and coverage.** Image-only visual execution is in PR #453. Add table-row/cell and cross-page/continuation handlers, then extend OCR coverage to additional region cases. Preserve source/version/location and keep fallback distinct from planner execution. Require explicit dispositions for supplied pages/regions; unsupported, omitted, clipped, failed, or ambiguous work remains unresolved.
3. **Prove the complete browser operator journey.** Exercise fresh, partial, and resumed planner runs through source navigation, add/remove/edit/review actions, visible incomplete states, and XLSX/DOCX/PDF exports. Inspect generated artifacts independently.
4. **Measure quality without tender leakage.** Build human-adjudicated labels and whole-tender development/validation/held-out splits. Report omission, false inclusion, split/merge, exclusion, citation, numeric fidelity, coverage, uncertainty calibration, latency, cost, and review burden. Use existing `examples/` for development only; do not call them held out or tune on the held-out set.
5. **Verify deployment constraints.** Establish a private deployment path compatible with persistence, authentication, file limits, runtime limits, OCR/native dependencies, and confidential-document handling, or document why local/private operation remains required. A successful upload is not a successful processing check.

Do not call Phase 1 v2 complete until the source-operation, browser-workflow, quality-evaluation, and deployment outcomes in the sequence below have evidence. A synthetic contract test proves workflow behavior only, not general tender quality.

### 1. Resumable local run path — complete (PR #447)

- Connect the encrypted local SQLite adapter to `analyzeTender`: persist a source/config-bound run, the validated task plan, work-unit state and completed outputs; save the final result before reporting success.
- Resume only when the reselected PDF fingerprint and pipeline/model configuration match. Revalidate a saved plan against the current parser inventory. Reuse only completed units with authenticated result artifacts; return running units to retryable and rerun them. Keep source verification and downstream validation in the resume path.
- A pipeline-version change alters the execution fingerprint intentionally. Runs created with the prior version are rejected for resume and must be restarted from the source PDF; do not silently reinterpret old work artifacts under new semantics.
- Propagate the opaque run ID in progress and let the browser remember only that ID keyed by the exact PDF SHA-256. Never store tender text or model output in browser local storage. Require the user to reselect the PDF after reload.
- Keep the store opt-in, encrypted, local/private and unavailable on ephemeral serverless filesystems. Document key handling, location, deletion, size and failure behavior. A persistence error must not be presented as a resumable run.
- Acceptance passed: the encrypted store persists a validated plan, page routing, visual extraction, native-text extraction results, and final output; the scripted pipeline interrupts during extraction, restarts the process, reuses the completed artifact, reruns only unfinished units, and retains deterministic requirement order. Wrong-PDF and changed-endpoint resumes are rejected before provider calls. The local browser also completed cancel/reload/resume through review and export.
- Limits: this proves local adapter behavior and the exercised synthetic paths. It does not provide hosted durability, broad failure-mode coverage, or real-tender quality evidence.
- Provider-failure acceptance passed: when one extraction batch fails after five earlier batches completed, the API returns a visibly incomplete draft and leaves the encrypted run paused; after a Next.js restart, it reuses five completed artifacts, retries only the failed batch, and persists a final completed result after recovery. The scripted test does not establish live-model quality or actual 42-page tender completeness.

### 2. Planner-driven source execution — native-text, vector-table, and OCR slices merged; additional source operations open

Native-text, vector-table, and OCR planner-selected handlers are merged. Continue by extending the same source-bound execution contract to other parser-known source types and document relationships. This is not a fixed tender format: the model decides which supported content and structure matter for each tender; unsupported proposals must remain explicit and unresolved.

- Include bounded, explicitly clipped native text-block candidates in the planner inventory. Bind every candidate to its parser ID, owning page, text, and known offsets. Validate that each proposed operation is compatible with the source kind; reject forged, ambiguous, duplicate, or incompatible references.
- Materialize stable, bounded work units from validated `native_text` actions and preserve their action/source relationships. The handler may send only selected block text, in source order, under the existing extraction schema. Returned quotes must pass the existing literal source/page checks; do not concatenate non-contiguous blocks into fabricated continuous evidence.
- Persist accepted results as authenticated artifacts and reconstruct ephemeral trace IDs when resuming. Reuse completed units only when source, configuration, and artifact validation match. Retry unfinished work without duplicating accepted results.
- Track handled, incomplete, unsupported, and fallback source coverage. Do not call unsupported OCR, visual, table, or cross-page actions complete. Use the legacy path only for uncovered content where safe, and record that fallback so coverage cannot be overstated. Avoid duplicate extraction for source blocks already successfully handled by the planner.
- Preserve prompt-injection boundaries, page/source identity, clipping and omission signals, ordering, cancellation, retries, request budgets, and the current human-review/export contract.
- Acceptance: scripted tests prove real planner input includes parser text-block IDs; wrong source kinds are rejected; only selected content reaches the handler; grounded outputs keep page/source links; completed units survive restart; remaining units retry; overlapping/unsupported/uncovered work stays explicit; the integrated result can be reviewed and exported without claiming unvisited content is complete.

PR #449 delivers planner-selected vector-table execution; PR #450 delivers planner-selected OCR extraction through the same action → validated source → bounded WorkUnit → persisted result → coverage contract. Image-region visual, table-row/cell, and cross-page/continuation planner actions remain unsupported or incomplete and must stay visibly unresolved. Never represent an unimplemented mode as completed work.

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
