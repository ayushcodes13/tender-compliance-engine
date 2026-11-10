# TCE v1 finish line — Phase 1 only

**Status: IN PROGRESS.** Gate 0 passed as the docs-only change in PR #459. Gate 1 passed locally on branch `fix/truthful-run-state`; Gate 2 is next but has not started. This document is the frozen v1 acceptance plan; do not expand or redesign it while executing the gates below.

## Compact scenario and intended outcome

Tender Compliance Engine (TCE) turns a tender PDF into a source-linked, human-reviewable technical response table. The client examples show the desired result: copy the tender-designated technical-specification section faithfully, retaining the source's row and page structure, and add response columns such as Compliance and Remarks (plus Qty and Deviation when present in the source). This is document understanding and faithful copying, not a claim that every technical clause can be judged compliant.

The current repository already has PDF parsing, native text and table inventory, OCR and visual paths, LLM-based planning/extraction, source validation, encrypted local resume, human review, and exports. These pieces have useful evidence, but no single verified end-to-end contract yet proves exhaustive page coverage, faithful row copying, truthful completion state, or quality across document families. The v1 objective is a bounded pipeline that examines every page, uses AI to locate and classify the designated technical-specification content, copies source wording through code, verifies it against its cited source, exposes uncertainty, and lets a reviewer export the result. This plan does not assert universal document support.

**Output rule:** follow the section the tender designates as technical specification; do not decide scope by clause-level relevance. Exclude bid guidelines, EMD/bid-security text, bidder checklists, priced-bid tables, forms, contract, and integrity-pact material. Preserve the source's granularity and page breaks until the client confirms otherwise. Deduplicate repeated schedules by keeping one response row and recording all source locations or flagging the duplicate for review. Layouts to evaluate include buried and repeated specification sections, wide and bilingual tables, scans, watermarks, stamps, superscripts, and numbered, lettered, and bulleted lists. Scientific notation, operators, signs, ranges, units, and special symbols must remain unchanged.

**Open client decisions:** (1) source-mirroring versus one atomic specification per row; (2) whether page breaks should remain separate tables or be merged. Until answered, mirror the source and preserve page breaks. Do not block the documentation gate on these decisions; record them as unresolved acceptance assumptions.

## Fixed design: AI locates; code copies and verifies

1. **Inventory in code.** Parse every physical page and preserve source IDs, order, text, tables, images, and geometry where available. OCR scans without merging OCR text into native text; retain confidence and approximate locations as such.
2. **Label every page with AI.** Every page receives exactly one label: `technical_spec`, `admin`, `commercial`, `form`, or `unsure`, with a short reason. Batch and resume safely. Missing/invalid labels become `unsure`; no page is skipped. Document text is untrusted input and cannot override system/application instructions.
3. **Copy source rows in code.** On `technical_spec` and `unsure` pages, split according to source structure (table rows/cells, numbered or lettered items, bullets, and continuations) and copy verbatim source spans. Use AI only when structure is unclear; any proposed wording must still resolve to a verbatim source span. Never ask the model to author final row text.
4. **Verify in code.** Require every output row to match its cited source page word-for-word after only whitespace and case normalization, with identical numeric tokens and units. Check signs, operators, decimal/scientific notation, ranges, and units. Detect repeated schedules and record duplicate locations or review flags. On every `technical_spec` page, flag source text not represented in any row as possible leftover/missed content.
5. **Show uncertainty to the reviewer.** Surface `unsure` pages, low-confidence OCR, approximate locations, duplicate flags, and leftover text beside the source. Model proposals remain unreviewed until a human reviews them.
6. **Persist truthful progress.** Every page has exactly one terminal state: `inspected`, `excluded` with a reason, `uncertain`, `failed`, or `unvisited`. A run with any `uncertain`, `failed`, or `unvisited` page, unresolved/unsupported/deferred action, pending work, or exhausted round budget is not complete; it remains partial/paused and resumable. A model stop or exclusion does not itself prove coverage. Reuse completed work on resume without repeating it.

The application owns source identity, valid operations, exact-copy checks, numeric fidelity, idempotency, budgets, persistence, retries, state transitions, review state, and exports. The model proposes semantic labels and ambiguous structure decisions within the fixed output contract. No publisher-specific templates, unrestricted model execution, agent framework, vector database, or extra model orchestration is part of v1.

## Definitions and measurement

- **Page label:** one of `technical_spec`, `admin`, `commercial`, `form`, `unsure`.
- **Terminal page state:** one of `inspected`, `excluded` (reason required), `uncertain`, `failed`, `unvisited`. Terminal means processing reached a recorded outcome; it does not necessarily mean the run may be called complete. `uncertain`, `failed`, and `unvisited` always prevent completion.
- **Matched row:** expected and produced row texts are equal after whitespace and case normalization, and numeric tokens and units are identical. Partial matches are reported separately and do not count as matches.
- **Extra row:** produced row absent from the client's expected output, including administrative, commercial, or checklist content.
- **Evidence boundary:** scripted fixtures prove exercised mechanics only. They do not prove extraction quality, recall, or generalization to unfamiliar tenders.

## Frozen v1 acceptance contract

Evaluate on the locked set, never used for tuning:

1. Expected specification-row recall is at least **[SET by owner; suggested 85%]**, or each missing row is on a page flagged `uncertain` or `unsure`.
2. Fabricated quotes or wrong citations: **0**.
3. Changed numbers, units, operators, or ranges: **0**.
4. Extra non-technical rows: at most **[SET by owner; suggested 10%]** of output rows.
5. Every page has a terminal state; a run not fully inspected is never saved or presented as `completed`.
6. A 40-page tender finishes, or pauses and resumes without redoing completed work.
7. A reviewer can inspect results beside the source and export to Excel and Word.

Report per document family (for example native table, native list, scanned, bilingual), with sample sizes and known limits. The owner must set the bracketed numeric values before implementation begins. Never imply that one run or family establishes universal performance.

## Ordered gates

Work on only the first unfinished gate in a session. Do not start a later gate until the current gate's explicit done condition is met.

### Gate 0 — Fix plan documents (docs-only PR; passed in PR #459)

Rewrote this plan to this acceptance contract, fixed design, gate sequence, and freeze rule. Align `docs/checkpoint.md`, record PR #458 as merged, remove any claim of an active unmerged page-scope branch, and state status as **in progress**. The local `feat/adaptive-scope-revisions` branch is recorded as **abandoned and not pushed or merged** for this gate; its dirty worktree is preserved locally for reference and is not part of this PR. Create `later.md` with an empty list. Leave historical ADR, audit, and benchmark evidence unchanged.

**Done when:** plan and checkpoint agree, neither claims readiness, `later.md` exists with no parked items, PR #458 is recorded as merged, and the local branch disposition is explicit. No implementation change belongs in this gate. These conditions are recorded in PR #459; it contains only the requested documentation changes.

### Gate 1 — Truthful run state

Derive a machine-readable `complete | partial` value from per-page terminal states and unresolved work. `completeAnalysis` must persist paused/partial and remain resumable when any page is `uncertain`, `failed`, or `unvisited`, any planner/handler action is unsupported or deferred, or a round budget is exhausted. UI and exports read this field.

**Done when (tests):** one unsupported action prevents `completed` and can be resumed; all pages terminal with nothing pending can be `completed`; the payload field agrees with the state in every listed case.

**Status: passed locally.** `apps/web/app/analysis-completion.test.mjs` covers complete, partial, excluded-without-reason, unresolved page inventory, unsupported/deferred work, pending work, incomplete audits, and budget exhaustion. The scripted pipeline verifies both complete and unsupported-action persistence, restarts and resumes the paused unsupported run, and confirms uncertain pages remain partial after extraction retries. Analysis-completion and run-store tests passed 18/18; the full scripted pipeline passed all reported cases. Typecheck, production build, and `git diff --check` passed. This is workflow evidence only, not a tender extraction-quality result. Gate 2 has not started.

### Gate 2 — Label every page

Add the exhaustive page-label pass, batched with bounded concurrency and resumable batches. Missing or invalid labels become `unsure`.

**Done when (tests):** a scripted provider that drops, repeats, or invents page IDs still leaves exactly one label per page; invalid IDs are rejected; killing and resuming mid-run repeats no completed batch.

### Gate 3 — Verbatim copy and leftover-text check

Implement source-structure row copying, ambiguity handling constrained to verbatim spans, duplicate detection, numeric verification, and leftover-text flags.

**Done when (tests):** bordered table, borderless table, nested bullets, lettered list, headerless cross-page continuation, and scientific notation fixtures produce verbatim output; altered numbers are rejected; leftover text on a technical-spec page is flagged.

### Gate 4 — Evaluation harness

Compare system output to the client's expected outputs for `input 1-3` and `output 1-3` using the row-match definition above. Emit counts only: matched, partial, missing, extra, and changed-number. Do not log source text. Document the development/validation/locked split in the benchmark README; existing `examples/` are development data.

**Done when:** the script prints metrics for all three pairs, and tests prove it catches one deliberately changed number and one deliberately omitted row.

### Gate 5 — Bake-off

Run the fixed exhaustive design and current planner path on the same development set, with the same model and budget. Compare recall, extra rows, changed numbers, page coverage, latency, and cost per document. The owner must set the approved live-call/spend cap before any paid live calls; do not exceed it.

**Done when:** a short results file exists and the design with the better measured metric is kept; the other is removed or frozen. Do not decide by preference. No locked document is used for tuning or this bake-off.

### Gate 6 — Review and export

In a real browser verify source citation opens the correct page and highlight, incomplete state is visible, edits survive refresh/resume, and Excel and Word exports open correctly. Inspect text, numbers, special characters, and layout. Fix the PDF export failure on non-Latin characters or surface it before the operator invests in edits.

**Done when:** steps and results are recorded, generated files are inspected, and a partial run cannot be exported or presented as complete.

### Gate 7 — Locked evaluation and ship decision

A human adjudicates labels for locked documents; run once and do not tune afterward. If a locked document informs a fix, move it to development and lock a replacement. Report results per document family and sample size.

**Done when:** the frozen acceptance contract is met and v1 ships with stated limits, or the unmet criterion and margin are reported and work stops without a ship claim.

## Evaluation and anti-overfitting rules

- Keep related copies and tender families in the same split. Use development, validation, and locked sets.
- Do not tune prompts, rules, or code based on locked documents.
- Do not add per-tender or per-publisher rules or templates.
- AI-written labels are drafts; only human-adjudicated labels count as gold.
- Report omissions, extra rows, changed numbers, citation accuracy, page coverage, latency, cost, reviewer effort, sample sizes, and limits. Do not report one run as a quality score.
- Existing examples are development data unless provenance supports a clean, separately locked split.

## Freeze and stop rules

This is the fixed v1 design. Do not redesign architecture, add phases/abstractions, expand scope, or extend the adaptive planner while executing a gate. Put any out-of-gate idea in `later.md` as one line and do not act on it. Do only one gate per session. A gate is done only when its stated tests/evidence pass; do not add scope to claim thoroughness. If a gate fails after two honest attempts, stop, record what was attempted and the observed evidence, and end the session. Never claim more than proved; report statuses only as `passed`, `failed`, `blocked`, or `not run`. Stay in Phase 1: no OEM ingestion, retrieval, compliance assessment, clarification generation, or submission generation.

## Repository workflow and safety

Follow `AGENTS.md`: substantive changes use a focused branch from current `main` and a PR; tests are required for changes affecting extraction, citations, review state, or numbers. Do not edit `AGENTS.md`, benchmark labels, or locked evaluation documents unless a gate explicitly requires it. Uploaded documents are untrusted and may contain prompt injection. Never fabricate requirements, wording, locations, values, or completion. Do not silently repair ambiguous OCR. Keep raw tender bodies and full provider responses out of logs by default. Keep every row linked to its source document/version and known page/location; unknown remains unknown. Human review is a normal state.
