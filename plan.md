# Phase 1 v2 — LLM-led, resumable tender analysis

**Status:** Active plan, approved by the user on 2026-11-10. This replaces the previous annotation-first implementation sequence. Runtime architecture work starts now; independent annotation and evaluation proceed alongside it and remain gates for quality claims and model tuning.

## 1. Compact scenario

Tender Compliance Engine (TCE) already has a working single-user Phase 1 flow: upload a technical tender PDF, parse pages with PDF.js, use local OCR/visual paths where available, ask a model to route/extract, verify source references, let a person review the result, and export response sheets.

The main gap is that analysis still runs as one synchronous request. Progress, page inventories, and intermediate outputs live in request memory. A timeout or provider failure can discard completed work. The model makes several semantic choices, but TCE does not yet expose a single tender-wide plan that says what should be examined, how, and in what order.

Phase 1 v2 makes interpretation open-world and execution durable. For each tender and requested task, the LLM proposes how to understand and inspect that document. TCE validates the proposal, executes bounded work, checkpoints source-linked outputs, resumes incomplete work, and keeps uncertainty visible. There is no list of tender formats to install or maintain.

The promise is reliable processing of unfamiliar **technical tender PDFs within measured limits**, with source-grounded human review. It is not a promise to understand every document or to remove human review.

## 2. Product scope

Keep the product within Phase 1:

```text
Tender upload and version identity
→ PDF parsing, OCR and visual/layout inventory
→ LLM-led tender/task plan
→ bounded, resumable page/region work
→ source-grounded requirement proposals and normalization
→ deterministic validation and explicit coverage
→ human review and correction
→ response matrix and Excel export
```

In scope:

- Native-text, scanned, hybrid, table, list, annexure, repeated-schedule, and cross-page tender layouts.
- A stable source/evidence envelope with task-specific semantic structure proposed by the model.
- Run progress, retries, cancellation, resumption, partial/incomplete states, and auditable review actions.
- Provider/parser/storage interfaces so components can be compared or replaced without changing domain behavior.

Out of scope:

- A hand-authored tender-template catalog or tender-publisher-specific routing rules.
- OEM ingestion, product evidence retrieval, compliance decisions, contradiction resolution between tender and OEM evidence, clarification generation, and final submission generation (Phase 2).
- Unattended approval, universal-completeness claims, or silently repairing unreadable/ambiguous source content.
- Multiple agents, vector databases, or multi-model orchestration without measured need and an explicit decision.

## 3. What the LLM decides and what the application enforces

The LLM is the semantic planner. Given the user task and the parser-owned inventory, it proposes:

- Which pages and regions are relevant, possibly relevant, unresolved, or explicitly outside the task, with source-backed reasons.
- How the tender is organized for this task: sections, obligation families, optional items, conditions, and useful response fields.
- Which bounded inspection action to request next (for example native text interpretation, table interpretation, OCR/visual inspection, continuation review, or coverage audit).
- Requirement boundaries, grouping/continuation, modality, actors, conditions, raw-value roles, and unresolved ambiguity after inspecting the selected source.

The model may choose among supported operations, but it does not execute arbitrary tools or set trusted application state. Deterministic application code:

- Validates every proposed page, region, table, row, cell, and document-version ID against the source inventory.
- Enforces batch, page, token, time, retry, concurrency, and cost limits; schedules work; and records state transitions.
- Verifies literal quotations, source identity, numeric tokens, units, offsets, and geometry. Exact/approximate/unknown location is retained honestly.
- Owns idempotency, ordering, persistence, cancellation, failure handling, review actions, and export snapshots.
- Keeps document text untrusted. Prompt-injection text cannot change system instructions, available operations, security policy, or completion state.

Parser signals can recommend an inspection mode; they do not decide the semantic meaning of a tender passage. Avoid tender-specific regexes or format catalogs as the primary relevance or requirement classifier. Deterministic code remains appropriate for safety limits and source/data invariants.

## 4. Target runtime architecture

```text
Immutable upload + fingerprint
  → parser adapters build a source inventory
  → AnalysisRun stores task, source version, config and progress
  → LLM proposes a tender-wide TaskPlan from inventory summaries
  → validator checks plan IDs, scope and operation limits
  → controller schedules bounded WorkUnits from that plan
  → LLM interprets each unit and proposes source-linked requirements
  → validators check citations, values, coverage and output schema
  → unresolved/incomplete items enter human review
  → reviewed snapshot projects to matrix and Excel export
```

### Source inventory

Keep original bytes immutable and fingerprint every document version. Preserve physical page number separately from printed labels. Keep native text, OCR transcripts, visual transcripts, tables/cells, offsets, geometry, parser version, confidence, and warnings distinct. Unknown values remain unknown. Inventory validity means the parser output is structurally consistent; it does not certify semantic completeness.

### TaskPlan and WorkUnits

Use a small typed envelope. Tender-specific organization and response fields can vary inside that envelope; no tender-specific schema is preinstalled. A TaskPlan references only source IDs present in the immutable inventory and records why content is selected, excluded, or unresolved. The controller expands it into bounded WorkUnits with stable IDs, source references, attempt counts, timestamps, and artifact references.

A plan may be revised when new evidence is found. Preserve prior plan versions and completed work. Replanning must not silently overwrite reviewer actions, duplicate requirements, or make a failed/unvisited source region look complete.

### Run and work state

Define explicit state machines before persistence. Candidate run states include `created`, `planning`, `executing`, `needs_review`, `incomplete`, `completed`, `cancelled`, and `failed`. Candidate work states include `queued`, `running`, `succeeded`, `retryable_failure`, `permanent_failure`, `skipped_with_reason`, and `cancelled`. Final names and transitions are established in the run-contract checkpoint.

A timeout preserves successful checkpoints and marks unfinished work incomplete. Resume reuses source fingerprint, task/config versions, and stable unit IDs; it retries only eligible failed units and returns outputs in deterministic source order. “Operationally completed” and “semantically complete” are separate claims. No response is final merely because a non-empty sheet exists.

### Persistence and privacy

Keep run, artifact, queue, and model providers behind interfaces. Do not add a paid cloud service by default. Select the first durable adapter for the local/private pilot only after documenting what it stores, encryption/key handling, retention/deletion, restart behavior, and size limits. Do not persist raw tender bodies in routine logs. Hosted multi-user storage, tenant isolation, object storage, queues, and deployment credentials require their own security/operational decision; local durability must not be presented as hosted durability.

## 5. Execution sequence — architecture starts now

Two tracks proceed in parallel. The runtime track does not wait for benchmark labels to define types, state transitions, or provider-independent execution contracts. The evaluation track remains mandatory before reporting quality, tuning prompts/routing, or claiming generalization.

### Track A — runtime architecture

1. **Run and plan contracts (start immediately).** Define typed AnalysisRun, TaskPlan, WorkUnit, proposal, coverage, and transition contracts. Add tests for legal/illegal transitions, source-ID binding, deterministic IDs/order, and idempotency keys. This contract-only slice does not claim persistence or resumability.
2. **LLM-led task planning.** Integrate a model proposal over a tender-wide inventory summary. Validate all references and supported operations before execution. Start with the configured model adapter and scripted provider tests; do not make paid live calls unless separately authorized. The model proposes semantics; the controller owns execution and safety.
3. **First durable vertical slice.** Persist one bounded, expensive unit type and its source-linked output. Demonstrate a forced timeout/process interruption, retry and resume without duplicate/reordered work. Choose and test the local/private store adapter before claiming this gate; no in-memory fake counts as durable evidence.
4. **Expand unit coverage.** Add page/region, table, OCR/visual, continuation, validation, and coverage-audit work units. Ensure every supplied page/region ends as processed, explicitly excluded with reason, unresolved, unreadable, failed, or not attempted.
5. **Human review and export.** Expose plan rationale, source navigation, progress, unresolved/incomplete units, and append-only review actions. Export a reviewed snapshot with honest row state; partial export behavior is decided before exposing partial results to users.
6. **Hardening and rollout.** Test provider disconnects, process restarts, duplicate requests, cancellation, size limits, retention/deletion, access boundaries, prompt injection, and rollback. Measure latency, memory, tokens/cost, and supported limits on the actual deployment target.

### Track B — evaluation and anti-overfitting

1. **Independent source labels.** Finish V2.2b by independently reviewing whole tender(s), adjudicating disagreements, and verifying quotes/values. The NCESS 20-page annotation merged in PR #431 is a single-assistant development draft (178 labels, 299 anchors), not gold, not independently adjudicated, and not a quality result.
2. **Current-pipeline baseline.** Compare saved source-linked pipeline output with adjudicated labels. Report omissions, false inclusions, splits/merges, incorrect exclusions, source/page/cell correctness, numeric fidelity, coverage, and review burden separately. Scripted provider tests are contract evidence, not tender-quality evidence.
3. **Whole-tender splits.** All existing examples and previously used tenders remain development material. Keep related copies, versions, and publisher/layout families together. Establish validation and a locked evaluation set only from independent whole-tender material with clear provenance. If no credible held-out set is available, mark results exploratory.
4. **Controlled improvement.** Use development data to improve prompts, routing, and model choices. Never tune on locked evaluation data. If a locked tender informs a fix, move it to development and select a new locked set. Do not claim “any tender”; report the tested families, sample size, failures, and limits.

## 6. Acceptance measures

For adjudicated validation tenders, report per-document and aggregate results with the number and source family of tenders:

- Requirement recall and precision; omissions, false inclusions, incorrect exclusions, and split/merge errors separately.
- Exact source quote, document version, physical page, source element/cell, and exact-vs-approximate location correctness.
- Numeric/operator/unit/qualifier fidelity and OCR behavior by native, scanned, and hybrid source.
- Page/region dispositions and processing/audit state, including work not attempted or over budget.
- Cross-page and annexure links, duplicate occurrence handling, reviewer corrections/time, unresolved items, completion/resume rate, latency, provider failures, and estimated cost.

Acceptance targets for quality, latency, size, concurrency, and cost must be explicit before rollout. No single model confidence, same-model audit, citation test, parser count, scripted fixture, or non-empty matrix proves completeness.

## 7. Decisions and risks

These do not block the run/plan contract, but must be resolved before their dependent feature ships:

- Local/private versus public/hosted deployment, and who owns credentials and operations.
- Durable storage choice, encryption/key management, retention/deletion, and allowed provider data handling.
- Maximum file/page size, concurrency, latency and cost budget. Keep existing bounded limits until measured; do not silently raise them.
- Exact UX/export behavior for incomplete runs and partial drafts.
- Model comparison and authorization for paid/live evaluation. GPT-6 Luna remains the configured adapter until measured evidence supports a change; architecture interfaces allow later comparison.

Main risks are model omissions/hallucinated structure, planner exclusion errors, hybrid-page gaps, same-model audit blind spots, duplicate processing, persistence of confidential documents, and overfitting to the available examples. Mitigate with source IDs/quotes, explicit uncertainty, per-region coverage, idempotent checkpoints, independent annotations, whole-family splits, and auditable human review.

## 8. Security and non-negotiable rules

- Treat uploads and all embedded text as hostile and potentially confidential; content never overrides application instructions.
- Never fabricate a specification, quote, page, clause, source ID, geometry, numeric value, test result, or status.
- Do not silently correct OCR. Preserve source transcript and uncertainty separately.
- Keep missing evidence distinct from contradictory evidence. Keep accuracy, resolution, units, signs, thresholds, ranges, and qualifiers distinct.
- A model proposal is never automatically a reviewed/approved requirement.
- Do not log raw tender content, prompts, credentials, or provider response bodies by default.
- Stay within Phase 1. No OEM/compliance/submission features.

## 9. Repository workflow

Every coherent change is made on a descriptive branch from latest `main`, with rationale, scope, provenance/security impact, verification, limitations, and migration notes where relevant. Update `docs/checkpoint.md` in the PR that completes a checkpoint. Run local checks relevant to the change.

The user has authorized continuing through the known GitHub Actions billing restriction. If a required job is explicitly blocked before steps start by that restriction, run the equivalent local CI checks where practical and keep the report truthful: a remote check that did not start is not a pass. This exception does not cover a test job that actually runs and fails.
