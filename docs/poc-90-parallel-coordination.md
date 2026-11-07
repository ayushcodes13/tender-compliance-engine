# POC90: three independent Goal Mode agents + ChatGPT integration

Status: active sprint contract, 2026-11-07. Base before this revision: `e0f9a44eaf27f0f0ff66426ee096873c10e9258f`. **All agents must use the SHA of main after this coordination PR merges**, never the historic base. ChatGPT is the **fourth participant** (architect/integrator), not one of the three coding agents.

## 1. Authority, product and success metric

Every agent MUST read `AGENTS.md`, this file, `docs/checkpoint.md`, `docs/architecture/ADR-0001-document-intelligence-redesign.md`, and the current open PR list before doing anything. `AGENTS.md` governs safety and PR-first engineering; `docs/checkpoint.md` remains the canonical product backlog. **This file temporarily overrides the chronological first-unchecked-checkpoint order for this sprint, including the usual requirement that each agent modify checkpoint.md.** Only ChatGPT integrates checkpoint and status updates later. Do not rewrite old history or mark unknown work done.

Product = **operator-assisted single-user client POC**: upload a tender PDF -> create source-linked, independently reviewable technical/supplier obligations -> reviewer checks/edits -> export blank OEM compliance/deviation/remarks in DOCX/XLSX/PDF. There is no supplier capability ingestion, evidence-backed compliance verdict, multi-tenant production service, RAG, agent orchestration or autonomous tender assessment. A useful, inspectable draft is the promise, NOT exhaustive source coverage.

"70% -> 90%" is a **gated planning estimate, not a measured completion ratio or accuracy**. Starting from the prior 70% estimate, award potential points only with evidence:

| Final gate | Potential incremental points | Required evidence |
| --- | ---: | --- |
| G1. Controlled execution | +6 | A real hash-verified tender completes end-to-end on a pinned code version, with a terminal response, timed phases, tokens, and reconciled trace. The completed 157.002-second IITG result on `26cc047` is historical evidence for this gate; any new code must not invalidate it. |
| G2. Precision + grounding | +7 | Scope false positives addressed on the full saved candidate set, original and novel admin cases excluded/review-only, all three critical page-11 service obligations retained, mixed clauses review-only, at least ten technical value/citation spot-checks and three flagged page-8 evidence gaps diagnosed; one controlled final post-integration benchmark if explicitly authorized and feasible, with no critical source corruption. Offline fixtures alone are insufficient to claim end-to-end generalization. |
| G3. Review and export | +5 | Browser review/editor workflow verified with scripted or saved result: correct cited page/quote/highlight/approximation; review invalidation; independent rows; remove/reset; DOCX/XLSX/PDF preserve source wording, numbers, grouping and intentionally blank supplier fields. |
| G4. Usable private pilot | +2 | Repeatable operator-led local startup and handoff, access gate, clean secrets, supported PDF/OCR limits, documented failure behavior and no silent loss of unreviewed text. Remote-hosted availability is a separate gate if required by the client. |

At 90% all four gates require evidence and **zero unresolved P0 correctness/safety issues**. Scores are not additive if G2 remains blocked; don't assert 90% simply because PRs were merged. Even 90% does not mean production-ready, independent client validation or complete recall. Provide the score as an assessment with its evidence.

## 2. Most recent confirmed evidence (historical run, NOT a new instruction to retry)

- Latest merged code before this coordination revision: `e0f9a44`; no PRs open at inspection.
- Completed IIT Guwahati 15-page tender analysis on `26cc047`, source SHA-256 `88d912e8d3172a99e8422cef2c185dc90692f6b0b1d70e6646f557a524f65967`: **157.002 seconds, 137,770 provider-reported tokens, 172 accepted rows (146 requirements + 26 sections), 9 classification-review candidates; 228 trace candidates reconcile**. Do not confuse two runs' combined 208,847 tokens with this run's usage.
- The original 20 administrative false inclusions and four adjacent cases were absent from the accepted sheet, and the three page-11 AMC/local service/spares obligations appeared source-grounded. Provisional page-11 evaluation: **14/16 literal anchors; manual PDF comparison reported 7/7 obligation groups semantically covered**. This is not exhaustive recall.
- **P0 failure:** at least 12 *different* administrative/commercial rows remained accepted (PAN/TIN, vendor registration/banker/PO history, PO terms, financial guarantee, delivery logistics/penalty and HSN/GST); 3 mixed/document clauses also accepted instead of review. The `no_administrative_scope_conflict` fallback on model-labelled `requirement` is a plausible code-level mechanism. Precise classification transitions must use saved source quotes, not this summary.
- **P1 provenance:** page-8 accepted requirements `req-86`, `req-90`, `req-92` reportedly have empty `sourceReference.sourceText`, empty element IDs and null offsets although literal PDF inspection matches their wording. Need distinguish exact source, OCR/visual-only fallback, multiple matches, and honest approximate provenance.
- All four general-extraction batches completed in the successful run, source page IDs recorded in the report. Coverage includes incomplete/possible/not-run audits; do NOT assert 100% source recall.
- The saved result lives in an ignored local tree under `apps/web/.local/benchmark-runs/iitg-20261107T142219Z/`; trace in ignored `apps/web/.local/forensic-traces/`. These exist on the user's local machine, **not necessarily in each isolated worktree or accessible to GitHub**. Inspect or explicitly report inaccessible. Do not copy raw tender files into Git or make up their contents.
- Vercel project author permissions, hosted model configuration, custom DNS and hosted OCR remain unverified/deferred. The target POC is a **private local operator-assisted demo**. Hosted client access would require an additional acceptance decision.

## 3. Worktree, ownership and concurrency rules — NON-NEGOTIABLE

There are **three coding agents A/B/C running concurrently plus ARCH (ChatGPT)**. Every agent must be given the same merged coordination commit and a distinct workspace. **Use isolated `git worktree` folders and branches, not merely branches checked out in one directory.** Each worktree has its own `.next` build, `node_modules` as appropriate, `.local` output and Git index. Check main and open PRs at start; don't pull other agents' unmerged branches. Never run cleanup/reset that touches other worktrees.

Example (adjust paths safely; don't overwrite an existing worktree):
```bash
git fetch origin main
git worktree add ../tce-poc90-a -b poc90/a-scope origin/main
git worktree add ../tce-poc90-b -b poc90/b-provenance origin/main
git worktree add ../tce-poc90-c -b poc90/c-client-journey origin/main
```
Each coding agent executes ONLY its own `git worktree add` command, not all three. If branch/worktree exists, inspect and reuse safely instead of deleting. Verify HEAD contains this file and the exact merged coordination SHA. Each agent only stages and commits its own owned paths.

**Exclusive write ownership** (read-only inspection across lanes is allowed):
- **Agent A: Scope/classification.** `apps/web/app/candidate-classification.ts`, `candidate-classification.test.mjs`, and **new** self-contained offline classification tests/utilities named `apps/web/app/poc90-scope-*`. Do not edit `actions.ts`, `source-document.ts`, benchmark golden labels, any UI/export file or shared docs.
- **Agent B: Source provenance/validation.** `apps/web/app/source-document.ts`, `source-document.test.mjs`, `candidate-evidence.ts`, `candidate-evidence.test.mjs`, `tiered-validation.ts`, `tiered-validation.test.mjs`, and **new** self-contained provenance tests/utilities named `apps/web/app/poc90-provenance-*`. Do not edit classification logic, `actions.ts`, UI/export or shared docs. Need an `actions.ts` contract change? Report a precise integration handoff for ARCH; do not cross ownership.
- **Agent C: Review UI, export and pilot walkthrough.** `apps/web/app/tender-mvp.tsx`, `page.tsx`, `new/page.tsx`, `globals.css`, `response-sheet.ts`, `response-sheet.test.mjs`, `response-sections.ts`, `response-sections.test.mjs`, `sectioned-exports.ts`, `sectioned-exports.test.mjs`, `pdf-export.ts`, `pdf-export.test.mjs`, `remark-verification.ts`, `remark-verification.test.mjs`, and **new** `apps/web/app/poc90-client-*` tests. Source/PDF drawer components under `apps/web/components` are C-owned if needed. Do not touch classification/provenance, `actions.ts` or shared docs. Use `127.0.0.1:3308` if manually launching app; DO NOT run `make pilot-start` or `pilot-stop` on its fixed 3307 because it may collide. Scripted pipeline dynamically allocates ports.
- **ARCH (ChatGPT): shared architecture and integration only.** Owns `docs/poc-90-parallel-coordination.md`, `AGENTS.md`, `docs/checkpoint.md`, `README.md`, `docs/architecture/*`, `apps/web/app/actions.ts`, `apps/web/app/api/analyze/route.ts`, `apps/web/scripts/verify-pipeline.mjs`, `benchmarks/**`, provider/concurrency/coverage modules and all otherwise-unassigned files. ARCH does not change another lane's owned files while they work; may make a strictly necessary integration PR after all lanes hand off.

**No cross-lane code writes.** If a true blocker requires a foreign file, submit an interface request (exact symbols, paths, expected type/behavior, regression) to ARCH through PR notes; keep work independent. No shared-file edits in any agent PR, including AGENTS/checkpoint/coordination/README. Only ARCH updates shared checkpoint status after integration; this explicit sprint exception overrides the ordinary AGENTS checkpoint-update rule.

Each agent can run local tests and scripted-provider tests (synthetic only). Each runs **at most one focused PR** if code changes are justified (title prefix `[POC90/A]`, `[POC90/B]`, `[POC90/C]`). Never merge, change another lane's branch, or create a chain of PRs. PR body includes original base SHA, current head, exact touched paths, root cause, tests, screenshots/artifacts when suitable, regressions, limitations, handoffs and explicit note whether live model was called (it should be **NO**).

No coding agent may run a new paid live tender analysis, retry the old run, change provider model, adjust timeout/batch limits, deploy, mutate Vercel/DNS/secrets, or build new persistent infrastructure. **One final full-tender paid run is reserved for a post-merge integration decision, by ARCH/user-approved operator only**. Saving money and avoiding repeated inconclusive results is part of the sprint.

## 4. Agent A acceptance: administrative scope

Start from saved **172-row** completed IITG result when accessible, not from the older 192-row result or invented quote strings. Diagnose at least 12 fresh admin accepted rows `req-6,7,8,9,21,25,26,28,29,31,32,33` and mixed `req-3,5,15` using exact original quotes and trace decisions. Preserve 20 original admin exclusions, four adjacent exclusions and page-11 `req-159,160,161` service obligations. Requirements should be equipment/product technical characteristics, technical documents and supplier fulfillment (including installation, calibration, AMC, training, spares and service presence). Exclude routine bidder identification, qualification, procurement accounting/financial/bid mechanics and pure delivery logistics. Mixed or insufficiently supported content is review-only with literal quote, not silently dropped.

Do NOT produce a tender-specific 12-string blacklist or assume absence of one admin keyword proves technical relevance. Avoid default-keeping a `requirement` merely because no blacklist matched, but also avoid suppressing unfamiliar legitimate technical criteria. Build source-grounded positive/negative counterexamples from *existing available evidence* plus synthetics; compare classification for ALL available saved candidates offline; report newly blocked technical candidates as possible false negatives. Source evidence invariants unchanged. One focused classification-only PR, or report a blocker if cannot justify safe correction.

## 5. Agent B acceptance: provenance/grounding

Diagnose the three cited page-8 `req-86/90/92` sourceReference cases in saved terminal result plus trace, if locally accessible. Check exact vs duplicate native quote, OCR transcript, visual extraction, genuine text blocks/cells and existing bounding boxes. An accepted requirement with no sourceText/ID/offset must not be represented to reviewer as an **exact grounded text citation**. It may be legitimate visual/OCR evidence explicitly marked approximate/review-only; don't invent text/IDs/offsets. Fix source reference generation/matching in owned helpers only if validated by fixtures; add tests for repeated passages, Unicode/engineering units, source cell identity, positioned OCR, unmatched visual content and empty source text. If the only repair requires `actions.ts`, report a minimal typed glue/interface for ARCH instead of editing it. No classification changes, paid model calls or benchmark reruns. One focused provenance-only PR or evidence report.

## 6. Agent C acceptance: client journey/export

Use saved *completed* real analysis if accessible or a clearly labelled scripted fixture. Verify supported upload -> completed sheet -> cited PDF page/quote/highlight or explicit approximate/no-box state -> reviewer check -> edit invalidates check -> independent obligations -> remove/reset -> DOCX/XLSX/PDF export. Inspect source values, page references where format requires them, units and numeric operators, long cells, grouping and blank OEM decision fields. Run a basic-auth and secrets visibility check with test values, source warning/cancellation/errors, responsive desktop/mobile review. Prepare a reproducible private local demo walkthrough that does not require private client files or provider spend. A necessary UI/export bug may yield one focused PR with screenshot and regression; otherwise just provide evidence. No backend/model changes or real provider calls.

## 7. Checks, review and integration

Each lane: `npm --prefix apps/web test`, `npm --prefix apps/web run typecheck`, `npm --prefix apps/web run build`, `npm --prefix apps/web run test:pipeline` (if it launches with isolated build/worktree), and `git diff --check`. UI lane adds browser/export proof; if tool/runtime unavailable, state that exactly, do not fake PASS. Scripts use dynamic test ports; manual servers must be isolated. Required GitHub `web` check on each PR must be green; Vercel author permission failure is tracked separately but does not excuse required CI failure.

**Integration order:** (i) all three agents submit evidence and optional PR; (ii) ARCH reviews diffs/evidence, no cross-lane edits, resolves handoffs, merges PRs sequentially only when required CI is green; (iii) ARCH writes minimum integration glue in a **separate PR** if needed and updates checkpoint; (iv) run final main CI and source-to-UI contract tests; (v) decide whether **one** controlled final live IITG run is justified/authorized; (vi) issue evidence-backed readiness score and P0/P1/P2 list. A replay of a saved model result is not fresh extraction quality; a single successful real run is not generalization.

**Stop rule:** after one round of three PR/evidence handoffs and one joint review, do not launch new autonomous goal-mode waves. Choose: pilot-ready locally, one narrowly scoped remaining blocker, or not ready. Need real-client sign-off and independently adjudicated broader tenders later.

## 8. Common handoff format

All agents end with:

```text
LANE: A/B/C
BASE SHA:
HEAD SHA:
PR: link or "none—no code change"
OWNED FILES CHANGED:
EVIDENCE USED: saved / synthetic / browser / direct-PDF inspection / real live [should be none]
TESTS: commands with PASS/FAIL/SKIPPED
ACCEPTANCE CHECKS: PASS/FAIL/UNKNOWN and supporting artifact paths
REGRESSIONS / FALSE NEGATIVE RISKS:
P0/P1/P2:
NEEDS ARCH HANDOFF: file + exact interface + reason
LIVE MODEL REQUESTS: 0
READY FOR INTEGRATION: yes/no
```

Do not copy private PDF text or confidential results into public GitHub comments. Reports must distinguish observed evidence from estimates and unknowns.
