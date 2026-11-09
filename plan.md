# Phase 1 v2 — Evidence-first tender intelligence plan

**Status:** Approved for incremental implementation as of 2026-11-10. Follow the canonical checkpoint order. This approval confirms Phase 1 scope, PDF-first acceptance, model-led interpretation without a template catalog, and the development-only treatment of the existing examples. It does not claim universal completeness or settle the partial-result UI/export contract or operational targets.

## Compact scenario

Tender Compliance Engine (TCE) is a Phase 1 product for turning technical tender documents into source-linked, human-reviewable requirements and a response matrix that can be exported. The intended input variety is open-ended: tenders differ in publishers, layouts, scans, tables, schedules, annexures, and wording. We should not need a hand-authored template for every tender. The model should interpret the tender in light of the task and propose the structure and obligations that belong in the result.

The current system already has substantial parts of that design: PDF.js parsing, page and source-element inventories, local OCR and visual extraction paths, model-led semantic classification, source quote/location checks, omission audits, review states, and exports. The problem is not that TCE has no architecture. The problem is that its orchestration is still a large synchronous request; it is tied to a tender-specific output contract and one configured GPT-6 Luna endpoint; its parser/coverage signals do not establish semantic completeness; and some real analyses still finish with incomplete pages, audits, or failed batches. The user's estimate that the product is “70–80%” is a useful motivation, not a measured accuracy score.

The redesign should preserve TCE's provenance and review strengths, make work durable and resumable, and let model interpretation flex to unfamiliar tender structures. The target is dependable handling of unfamiliar **technical tenders**, with honest incomplete and review states—not a claim to understand every document or to eliminate human review.

## 1. Product goal and boundaries

### Goal

For a technical tender and the task “prepare a technical response matrix,” produce atomic, source-grounded proposals for technical and supplier-fulfilment obligations; account for every input page/region; preserve uncertainty; support human correction; and export the editable matrix with truthful per-row review state.

### In scope

- Tender PDFs with native text, scans, mixed native/image pages, complex or borderless tables, repeated schedules, annexures, nested lists, cross-page tables/clauses, and inconsistent page numbering.
- A common document/evidence model that parser adapters can populate. PDF remains the first production adapter. Add DOCX, XLSX, or image input only after the examples and acceptance criteria show that a format adapter is needed; do not confuse file-format support with tender-template support.
- Dynamic interpretation of which passages are technical requirements, supplier deliverables, headings, optional items, or administrative instructions, based on the tender and the requested output.
- Source-linked requirement proposals, uncertainty/review workflow, matrix projection, and Excel export.
- Durable progress, retry, cancellation, and resumption at page/region/batch boundaries.

### Out of scope

- OEM evidence ingestion, vendor compliance decisions, contradiction resolution between tender and OEM evidence, clarification generation, or final submission preparation (Phase 2).
- Universal extraction guarantees, automatic acceptance without review, a catalog of tender-specific templates, or silently converting unreadable content into confident text.
- Adding agents, vector databases, or multi-model orchestration before a measured need and evaluation result justify them.

## 2. Current baseline and evidence

The accepted architecture decision describes a TypeScript/Next.js application with PDF.js as the production parser, a source inventory, vector-table reconstruction, local Tesseract/Poppler OCR where available, model interpretation, deterministic source verification, and review/export. It also identifies the broad in-process orchestration and lack of durable jobs/persistence as architectural limits ([ADR-0001](docs/architecture/ADR-0001-document-intelligence-redesign.md)).

Current main also includes:

- A `SourceDocumentModel` with document/version fingerprints, pages, native text blocks and offsets, OCR/image regions and confidence, table/row/cell identifiers, geometry, and exact/approximate evidence distinctions.
- Model-led page routing and semantic requirement classification. Earlier brittle regex screens were removed; the model makes the meaning decision while code checks source grounding and output contracts.
- Separate native-text, vector-table, OCR, and visual-page paths, plus text and table-row/image omission-audit calls.
- A coverage/review ledger, manual review and correction, saved review state, and DOCX/XLSX/PDF export paths.
- Model timing, failure categories, bounded concurrency, partial source-grounded recovery, and explicit warnings when coverage is incomplete.

The remaining evidence is a reason to redesign the runtime, not proof that the product is generally accurate. Recent 42-page work produced a reviewable draft but still reported clipped routing context, uncertain pages, unmapped table rows, and pages with incomplete omission review. A later request reproduced a provider connection failure after completed batches; recovery work now preserves usable verified results while retaining failed pages as incomplete. These are individual runs and do not establish a general recall or precision score. See the dated evidence in [docs/checkpoint.md](docs/checkpoint.md) and the source-free benchmark notes in [benchmarks/representative-tenders/README.md](benchmarks/representative-tenders/README.md).

The companion Bynd repositories suggest reusable patterns, not a blueprint to copy: section-scoped PDF extraction plus a second anchor audit (Industry Reports Agentic); page summaries and selective vision inspection (Chat); query-directed retrieval with citation enrichment (table_grid); and combining layout parsing, continuation clues, model judgment, and structural table alignment (ContinuousTableMerging). TCE should adopt the evidence and routing ideas while retaining its tender-specific human-review and provenance requirements.

## 3. Design principles

1. **Open-world input, task-bounded output.** The system may encounter unfamiliar tender layouts and terms. The user's task defines what to produce; the input format or publisher does not define a template.
2. **Model for meaning; code for invariants.** The model proposes scope, semantic roles, grouping/splitting, and useful structure. Code verifies that sources, IDs, quotes, offsets, page references, and workflow transitions are valid. Numerical comparisons, if introduced in a future phase, use deterministic domain logic.
3. **A stable evidence envelope, flexible semantics.** Every proposal has a stable ID, task/run identity, review status, and one or more source references. Tender-specific categories/attributes can be proposed dynamically inside that envelope. Do not let an open schema erase provenance or make the review/export contract untyped.
4. **The parser reports what it saw; it does not certify completeness.** Keep native text, OCR transcript, visual transcript, table structure, and coordinates distinct. Record parser confidence and unknown/approximate locations honestly.
5. **Coverage is explicit.** Every page and inspectable region receives a disposition and processing/audit state. “Not selected,” “unreadable,” “not attempted,” and “no requirement found” are different states.
6. **An audit is evidence, not a guarantee.** A second call to the same model can share the first call's blind spots. Label audit provenance and evaluate omission recovery against adjudicated cases.
7. **Partial progress is durable and truthful.** A timeout or provider failure must not discard completed source-verified work or turn unfinished work into success. Resuming must not duplicate or reorder proposals.
8. **Review is part of the product.** Unreviewed, ambiguous, OCR-warning, incomplete, and needs-clarification states remain visible and actionable. No requirement is pre-approved by model confidence alone.
9. **No overfit claims.** Split data by whole tender (and, where possible, publisher/layout family), never by page alone. Documents used to tune prompts or code are development data, not untouched evaluation data.
10. **Protect tender content.** Uploaded files are untrusted and confidential. Document text cannot override system instructions; logs and evaluation artifacts must avoid retaining source text or secrets unnecessarily.

## 4. Target architecture

```text
Upload and version
  → format/parser adapters
  → canonical source inventory and parse-quality report
  → durable analysis run and page/region work units
  → task interpretation and tender-wide structure proposal
  → model-led scope/routing and atomic requirement extraction
  → source, coverage, numeric/OCR, and omission validation
  → review queues and source viewer
  → reviewed response matrix and export snapshot
```

### 4.1 Document and source inventory

Keep original bytes immutable and identify each version by a cryptographic fingerprint. Produce a parser-owned inventory with stable IDs for document version, physical page, text block, visual/image region, OCR region, table, row, cell, and cross-page continuation candidate. Preserve printed page labels separately from physical PDF page numbers.

Each source element should retain, when actually known:

- Exact extracted text or transcript and its extraction method (native, OCR, or visual proposal).
- Page-local offsets and offset convention; bounding box and coordinate system; table/cell relationships; parser confidence and warnings.
- Whether text/location is exact, approximate, or unknown; OCR and image-region disposition; parser version and relevant configuration.
- Relationships between headings, paragraphs, list items, cells, and continuation candidates as proposals with evidence, not silently asserted hierarchy.

Inventory validation checks structural consistency (page sequence, IDs, offsets, references, geometry, OCR links, table relationships). It must say clearly that structural validity does not prove all meaningful regions were detected.

### 4.2 Durable analysis orchestration

Introduce an `AnalysisRun` boundary separate from the upload route/UI. Persist the run request, source fingerprint, stage, per-page/region work state, attempts, provider result metadata, warnings, and references to source-linked outputs. Store source files and derived artifacts through access-controlled storage adapters. Select the job store, artifact store, and worker/queue after measuring deployment constraints and document-sensitivity requirements; keep those behind interfaces.

Make work units bounded and idempotent: inventory page, routing group, table/page extraction, coverage audit batch, verification batch, and export preparation. A retry may reattempt a failed unit without repeating successful units. Ordering and stable IDs must be deterministic on resume. Cancellation is explicit. A run may be operationally complete while its semantic coverage is still incomplete; UI wording and state must distinguish those.

### 4.3 Task and structure discovery

Start with a task contract such as “prepare a technical response matrix from this tender.” Give the model a tender-wide map (document outline, page/region summaries, detected tables, annexure links, parse warnings) and ask it to propose:

- Which kinds of information belong in this task's result and why, with source anchors.
- A task-specific organization (sections, technical items, service/delivery obligations, optional requirements, conditions, exclusions, and useful matrix attributes).
- Ambiguities or decisions that should remain open for the reviewer.

Validate the proposal and keep it revisable. Do not let a proposed schema dictate which source content is considered relevant. Use a stable proposal envelope for downstream review and allow the semantic fields to vary only where the UI/export contract can preserve them.

### 4.4 Routing and extraction

Use layout/parser signals to decide what inspection mode is appropriate, not to make the final semantic decision. Model routing may rank regions as relevant, possibly relevant, explicitly excluded with a source-grounded reason, or unresolved. Missing/failed routing is not exclusion.

Extract in source-bounded page/region batches. Use text when it faithfully carries structure; include page images for scans, ambiguous layouts, or tables where visual grouping changes meaning. Keep page/table/cell context and adjacent continuation context. Treat prompt-injection text inside documents as source content only.

Each requirement proposal should be independently assessable where the source supports a split. It carries literal source quotation(s), parent/group/continuation links when supported, task-specific interpretation, optionality/modality/conditions if evidenced, uncertainty, and review status. Preserve split proposals as separate decisions; preserve a combined obligation only when the source expresses one indivisible condition. Never add a value, unit, scope, modality, or supplier commitment that the source does not support.

### 4.5 Tables and cross-page structure

Treat table detection, cell reconstruction, semantic interpretation, and cross-page continuation as related but separate operations. Keep raw parser table/cell evidence. Allow a model to propose header meaning, row role, continuation, and obligation boundaries; validate all returned cell/page/region IDs against the inventory. Align or merge structures only with explicit evidence and retain original table identities/citations after a merge. If columns or scopes differ, preserve separate tables and flag review rather than forcing a shared schema.

### 4.6 Evidence, coverage, and validation

Maintain two complementary ledgers:

- **Source coverage ledger:** every page/region's routing disposition, parse/OCR state, extraction state, audit state, and reason for any incomplete/skipped/unreadable work.
- **Proposal ledger:** each extracted/recovered/rejected/duplicate/ambiguous proposal, its source references, validation outcomes, and review actions.

Validation layers:

1. **Structural/source checks:** referenced elements exist; quote is literal and resolves to the stated page/region; offsets and boxes are parser-derived or explicitly approximate; model output cannot invent source IDs or geometry.
2. **Fidelity checks:** preserve digits, operators, signs, units, qualifiers, negative/optional wording, durations, conditions, and modality; OCR hazards lower certainty and do not silently correct the transcript.
3. **Semantic coverage checks:** compare every supplied source unit against proposals for omissions, over-merging, incorrect exclusions, and misclassification. Record which model/prompt/method performed this audit. Same-model agreement remains advisory.
4. **Human review:** prioritize unresolved/high-impact items, provide source navigation/highlights, allow add/edit/remove/reclassify with audit trail, and retain the original evidence separately from operator wording.

No final “complete” label may be based solely on a nonempty matrix, a passing citation check, parser structure counts, model confidence, or an audit that found no gaps.

### 4.7 Model strategy

Keep model calls behind role-based adapters so candidates can be compared without changing domain logic. Evaluate at least a capable text/reasoning model, a vision-capable model, and a mixed route on identical examples. Use stronger models where they materially improve semantic scope or layout interpretation; use cheaper models for simpler steps only after measured quality is acceptable. Route image input when visual evidence matters; do not pay to send every page as an image without an evaluation showing benefit.

Before selecting production defaults, compare exact-source grounding, omission/false-inclusion rates, split/merge correctness, OCR/table behavior, completion rate, latency, token usage/cost estimate, provider failures, and reviewer correction burden. An architectural model interface does not require multiple models at runtime.

### 4.8 Security, privacy, and retention

Treat every upload as hostile and potentially confidential. Validate format, size, page count, and decompression/resource limits before parsing; add malware scanning at the production boundary where the hosting environment supports it. Enforce organization/project authorization when reading or mutating source files, run records, review actions, and exports. Protect files and derived artifacts in transit and at rest; keep provider credentials in server-side secret storage; do not put source text, prompts, filenames, tokens, or secrets in routine logs. Define retention and deletion for original uploads, OCR/layout derivatives, partial run outputs, and exports, including cleanup after abandoned/failed jobs. Record model/provider, prompt/schema, parser version, and run configuration needed for audit without retaining raw model payloads by default. Maintain prompt-injection tests and treat document instructions as data.

## 5. Example corpus and evaluation without overfitting

The existing `examples/` PDFs are the initial available document pool; no additional private tenders are required to write this plan. Their presence is not by itself a gold set. The repository's current benchmark notes state that several existing annotations are partial and that some documents/runs have already informed fixes.

Before tuning:

1. Fingerprint and inventory all example tenders; record publisher/source, file family, page count, native/scanned/hybrid characteristics, table types, annexures, and known failures without copying full text into committed notes.
2. Split by whole tender into (a) development/tuning, (b) validation, and (c) locked evaluation. Keep related copies/versions and near-duplicate documents in one split. If the corpus is too small for a credible locked set, label the result exploratory and acquire additional public, licensed, or user-approved examples later.
3. Independently annotate selected whole tenders at source-region level: expected technical/service obligations and non-requirements; atomicity/grouping; exact quote/page/cell; numeric/operator/unit values; uncertainty and acceptable human-review outcome. Adjudicate disagreements before scoring.
4. Never use locked evaluation documents to revise prompts, heuristics, parser thresholds, or model routing. If they influence a fix, move them to development and designate a new locked set.
5. Report per-document and aggregate results with sample size and limitations. Synthetic/provider-mock tests validate contracts, not live model accuracy.

### Required measures

- Requirement recall and precision against adjudicated source obligations; separately count omissions, false inclusions, merges/splits, and incorrect exclusions.
- Citation correctness: exact quotation, physical page, source element/cell, and exact-vs-approximate location accuracy.
- Numeric/operator/unit fidelity and OCR error behavior by native, scanned, and hybrid input.
- Coverage: pages/regions fully processed, explicitly irrelevant, unresolved, unreadable, failed, or not audited; no hidden denominator limited to detected vector rows.
- Cross-page and annexure linkage quality; duplicate handling without collapsing independent requirements.
- Review burden: corrections, additions, removals, reclassification, time per tender, and unresolved queue size.
- Reliability and operations: completion/resume rate, provider failures, stage latency, maximum input/batch sizes, tokens and estimated cost, cancellation and retry correctness.

Targets for recall, precision, cost, and completion time must be agreed before implementation is accepted. Grounded source references and truthful incomplete states are hard invariants, not tunable trade-offs.

## 6. Delivery phases and gates

| Step | Work | Exit evidence |
|---|---|---|
| 0. Plan approval | Confirm scope and design choices below; reconcile execution order with `docs/checkpoint.md`. | Approved plan and updated canonical checkpoint before implementation. |
| 1. Baseline and evaluation protocol | Inventory `examples/`, document existing evidence/known failures, create whole-tender splits and source-level annotations, record current pipeline baseline without treating partial samples as accuracy. | Reproducible manifest, annotation protocol, locked-set handling, baseline report with explicit limits. |
| 2. Domain and run contracts | Define source elements, analysis-run states, work-unit states, proposal envelope, coverage ledger, review actions, export snapshot, idempotency, version compatibility, and how existing review sessions/exports are read or migrated. | Reviewed schemas/state transitions and migration/retention/security plan; existing saved review work remains recoverable or has an explicit migration path. |
| 3. Inventory and parser boundary | Isolate PDF parser/OCR/layout adapters; validate stable source inventory; preserve native/OCR/visual provenance and unknown/approximate data. | Golden source-reference tests and parser comparisons on adjudicated regions; no unmeasured parser swap. |
| 4. Durable resumable orchestration | Move synchronous orchestration behind run/job interfaces; persist each bounded unit and its outputs; add retry, cancellation, resume, progress, and partial-result semantics. | Fault-injection evidence for provider disconnect/timeout/restart; source-order deterministic resume; no duplicate rows; incomplete units stay visible. |
| 5. Task-led model workflow | Add tender-wide structure/scope proposal and flexible semantic fields within the stable evidence envelope; add interchangeable text/vision model adapters and controlled model comparison. | Schema/source-ID validation, prompt-injection tests, comparative evaluation on development/validation data, no locked-set tuning. |
| 6. Coverage, validation, and tables | Integrate source-region coverage accounting, omission audits, table/continuation proposal validation, citation/numeric/OCR checks, and human recovery paths. | Recall/precision and citation/fidelity measurements on adjudicated validation tenders; all unprocessed content represented as incomplete/review. |
| 7. Review and export | Present run progress, source coverage gaps, uncertainty, proposal provenance, saved review actions, and export projection. | End-to-end upload → resume → inspect evidence → edit/review → export acceptance on representative tenders; verify old saved reviews remain accessible or are migrated. |
| 8. Locked acceptance and rollout decision | Freeze code/model/prompt configuration, run locked whole-tender evaluation, assess quality, privacy, latency, and cost against approved targets; stage a reversible rollout and retain a rollback path. | Signed acceptance report; failure analysis; migration/rollback evidence; go/no-go; no broad “any document” claim beyond tested scope. |

Each implementation step should be a focused branch/PR with relevant behavior tests, a checkpoint update in the same PR when a checkpoint is completed, source-provenance impact, verification evidence, and limitations. Do not use a green scripted pipeline as a substitute for held-out live-model and human-adjudicated evidence.

## 7. Release and acceptance rules

- A proposal is never accepted automatically because the model is confident.
- A source quote that cannot be verified remains approximate/uncertain or is rejected; never fabricate page, box, source cell, or text.
- All pages and detected/known regions have an explicit disposition. Any missing route, parse failure, over-budget audit, or provider error remains visible and blocks a claim of complete processing.
- Completed work may be reviewed/exported as a partial draft only if incomplete work is conspicuous and each row's review state is represented; define this product behavior before implementation.
- No requirement is marked reviewed unless a user took that action; preserve reviewer state across save/resume/export.
- No model/parser change ships based only on tuned examples; require locked-set evidence and regression coverage for prior critical misses.
- No Phase 2 behavior is introduced under this plan.

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| A stronger model still misses content or hallucinates structure. | Source anchors, region coverage, omission evaluation, abstention, and review; compare models empirically. |
| Dynamic schema creates a weak or inconsistent UI/export contract. | Keep a small typed proposal/evidence envelope; permit flexible task semantics without unbounded database/UI fields. |
| Parser sees only part of a hybrid page. | Inventory native text, image regions, OCR attempts, and visual-review gaps separately; evaluate by modality. |
| Same-model audit agrees with extraction's blind spot. | Label it advisory; use independent source annotations, different audit framing/model where justified, and human review. |
| Durable jobs add scope and operational complexity. | Select minimal storage/queue design from deployment and confidentiality requirements; establish local adapter and failure-injection contracts first. |
| Example-driven fixes overfit publisher/layout patterns. | Whole-tender holdouts, blind annotation, publisher/format stratification, locked sets, and explicit small-sample limitations. |
| Long tender costs/timeouts remain high. | Durable bounded work, stage telemetry, model routing experiments, retry budgets, token/cost controls, and user-visible progress. |

## 9. Confirmed defaults and open decisions

The product owner has approved the plan direction and the following defaults are reflected in the active Phase 1 v2 task:

1. **Confirmed — product scope:** keep Phase 1 focused on technical tender intake through reviewed response matrix and export. OEM compliance and other Phase 2 behavior remain out of scope.
2. **Confirmed — input coverage:** PDF (native, scanned, hybrid, tables, and annexures) is the first acceptance surface. Add office formats only when evidence and an explicit product decision justify an adapter.
3. **Confirmed — interpretation and output:** do not use a catalog of tender templates. Let the model propose task-specific structure and categories inside stable source, review, and export contracts; use deterministic code for invariants and provenance.
4. **Open — partial-result contract:** incomplete work and uncertainty must remain visible for human review. Decide the exact partial-draft UI/export behavior before implementing that workflow; a partial result must never be represented as complete.
5. **Open — operational target:** after the baseline, agree maximum tender size, completion-time/cost envelope, and supported deployment/storage constraints. Do not invent these targets before measurement.
6. **Confirmed — evaluation corpus:** treat `examples/` and previously used tenders as development material. Keep related copies/versions in one family and do not claim a locked evaluation until independent whole-tender material is available and protected from tuning.

## 10. Source documents informing this plan

- `AGENTS.md` — product scope, evidence rules, security, testing, PR workflow.
- `docs/architecture/ADR-0001-document-intelligence-redesign.md` — accepted incremental architecture direction and current runtime limitations.
- `docs/checkpoint.md` — current implementation sequence and dated live-run evidence.
- `benchmarks/representative-tenders/README.md` — source manifests, partial annotations, evaluation limits, and holdout guidance.
- `apps/web/app/source-document.ts`, `apps/web/app/actions.ts`, and `apps/web/app/model-provider.ts` — current source model, end-to-end orchestration, and single-model configuration.
- `examples/` — existing tender sample pool; source files are evaluation material, not proof of accuracy.
