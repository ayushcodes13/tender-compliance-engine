# POC 90: three-lane parallel execution contract

Status: active coordination plan, 2026-11-07. Initial engineering baseline: main 26cc04769f13cad92d5e498570c80e34b13dcdc3 (PR #389). Future lanes must branch from the main SHA containing this coordination document.

## Authority and scope

Read this file, AGENTS.md, docs/checkpoint.md and docs/architecture/ADR-0001-document-intelligence-redesign.md before work. AGENTS.md continues to govern engineering safety and PR requirements; docs/checkpoint.md remains the canonical checkpoint plan. This file is the temporary **execution/ownership overlay** for the client POC sprint. Do not interpret historical checked boxes as current acceptance evidence.

Phase 1 only: tender PDF -> source-linked technical requirement candidates -> human review -> blank OEM response sheet -> DOCX/XLSX/PDF exports. No OEM evidence matching, autonomous compliance verdict, RAG, accounts/multi-tenancy, worker/queue, or unrelated product features. This sprint targets a **single-user, operator-assisted client POC**, not a general-production service.

## How to interpret 70% -> 90%

70% was an approximate readiness assessment, not a measured repository metric. These **incremental 20 readiness points** are a planning score, awarded only after the evidence is reviewed. They do not establish model recall or production readiness:

| Workstream | Possible gain | Evidence required |
| --- | ---: | --- |
| A. Execution reliability | +6 | One controlled full IIT Guwahati run reaches a terminal completed response sheet on pinned code; measured stage/batch timing, response count, usage and final trace. A timeout gives 0 here. |
| A. Extraction correctness | +7 | In that completed run, all 20 previously flagged administrative rows are outside the accepted matrix; the three page-11 AMC/local support/spares obligations are present with literal source evidence; direct source/PDF inspection records judgments on these and at least ten varied citations/technical values (agent-reviewed, with later independent human sign-off still pending); inspect the seven-group/16-anchor provisional evaluator without mislabeling it exhaustive recall. Zero fabricated citations and no observed critical-value corruption in the sample. |
| B. Review/export journey | +5 | Browser walkthrough from a real saved extraction or controlled scripted upload to source inspection/highlighting, reviewer decision, edit invalidation, removal/reset and export; compare DOCX/XLSX/PDF against reviewed sheet for requirement counts, units, blank OEM fields and sources. Browser evidence and defects reported. |
| B. Pilot operability | +2 | A repeatable private local operator-led start/upload/review/export procedure, clean secret handling and fail-closed access tested; explicit client limitations and a usable demo handoff. Remote hosting/custom domain is not assumed ready. |

**90% is conditional, not a deadline promise**: all four gates must have evidence, no blocking critical issues, no falsely green CI and no incomplete analysis masquerading as success. If A's paid run fails, report below target; do not inflate the number by merging PRs. A non-developer customer's sign-off and broader gold-set coverage remain beyond this milestone. Do not claim exhaustive tender completeness.

## Concurrency protocol — mandatory for all three

1. Begin from the same merged coordination baseline on **three separate git worktrees/branches**. Never share a working directory or uncommitted changes. Read open PRs before starting and again before requesting merge.
2. Exactly one owner per code file. Changes outside a lane's ownership require a handoff and a decision by the Architect; do **not** silently edit another lane's files. Do not cherry-pick unreviewed work across lanes.
3. Each coding agent operates in Goal Mode **only inside its lane** and may diagnose, implement, test and open **one focused PR**. No automatic merging, unlimited retries, unrelated cleanup, or multiple PR chains. A lane with no justified code change reports evidence without fabricating a PR.
4. Coordination and status are communicated through each PR description (prefix title [POC90/A] or [POC90/B]), with commit SHA, changed paths, tests, blockers and required handoffs. Do not concurrently edit this document, AGENTS.md, docs/checkpoint.md, README.md or the architecture ADR.
5. A dependency or edit conflict is **not** an invitation to take over. Stop the affected subtask, document the interface requested, and continue only independent work.
6. Do not edit requirements or source to make an evaluator pass. No secret keys, private tender PDFs, customer exports, raw source text or full model responses in committed test fixtures or logs.
7. No unbounded live model calls. Only Agent A owns the IIT Guwahati paid benchmark, maximum **one** full run after preflight on the selected SHA. No automatic retries. Agent B uses saved artifacts/scripted provider/browser fixtures and must not consume live model tokens.
8. Integration order: each lane finishes and submits evidence; Architect inspects both PRs and final acceptance; required web CI must be green; merges are serialized, followed by checking final main CI. If shared API/types need changes, coordinate explicitly before merge. A passed synthetic test is not a real-tender result.

## Lane ARCH — ChatGPT, architecture/integration owner

Owned files during setup: docs/poc-90-parallel-coordination.md, AGENTS.md and docs/checkpoint.md. After setup merge, **freeze** these shared documents until integration. May read every file but does not implement pipeline/UI code, upload tenders, make paid calls, or run browser/model/PDF tests for other lanes. Owns acceptance matrix, technical risk assessment, scope/interface decisions, PR review and final go/no-go assessment.

Deliverable: merged coordination plan, two independent Goal Mode prompts and final integrated evidence report. Architecture recommendations do not count as successful implementation.

## Lane A — Agent 1: extraction reliability, real-tender evaluation

Exclusive code ownership (only if needed): apps/web/app/actions.ts; document-input.ts; model-provider.ts; model-timing.ts; concurrent-map.ts; concurrent-waves.ts; analysis-stream.ts; candidate-classification.ts; coverage-ledger.ts; source-row-audit.ts; text-page-audit.ts; corresponding focused tests; apps/web/app/api/analyze/route.ts; apps/web/scripts/verify-pipeline.mjs; benchmarks/**. Agent A also owns existing ignored local benchmark, trace and quality artifacts.

Goals:
- Preflight main SHA, existing 15-page IITG source SHA 88d912e8d3172a99e8422cef2c185dc90692f6b0b1d70e6646f557a524f65967, model configuration, safe timing/forensic logging, output paths and GitHub CI.
- Execute at most **one** full, paid, controlled benchmark. On success compare 20 administrative rows, 4 adjacent rows, 3 page-11 obligations, provisional 7 groups/16 source anchors, numerical/citation errors, trace reconciliation, tokens and runtime. No score without a completed result.
- On failure preserve event/page IDs/timings/partial trace and provide root-cause hypothesis with uncertainty. Do not silently retry or replace actual results with offline classifier replay.
- A code fix is justified only for a reproducible, lane-owned P0 that prevents acceptance; create one focused PR with synthetic regression. Do not widen timeouts or change batch limits reflexively. Distinguish failure from quality evidence.

Forbidden: edit UI/export code, add hosting/DNS features, alter shared docs, change classification solely to match one golden file, run additional paid benchmarks. Report interface requests to ARCH.

## Lane B — Agent 2: client walkthrough, review/export, operator handoff

Exclusive code ownership (only if needed): apps/web/app/tender-mvp.tsx; page.tsx; new/page.tsx; relevant browser UI components; globals.css; response-sheet.ts; response-sections.ts; sectioned-exports.ts; pdf-export.ts; remark-verification.ts; corresponding focused UI/export tests and browser test artifacts. May read the rest but must not modify A-owned extraction or CI pipeline scripts.

Goals:
- Use existing saved **completed** analyses and/or isolated scripted model fixtures to test the actual client workflow. Do not claim a replay constitutes fresh model extraction.
- Verify correct PDF/quote/page/highlight display; source uncertainty and human review; edit invalidates prior reviewed status; remove/reset; independently assessable requirement rows; export integrity and blank supplier compliance fields. Include 42-page/93-row saved client-style example if it is accessible and lawful to use.
- Check local startup, basic-auth gating, clear error handling, supported PDF limits and a private demo handoff. No deployment credentials or environment file commits. Treat hosted Vercel access, custom domain and scan-only hosted OCR as explicitly deferred or blocked, not silently complete.
- If genuine POC-blocking defect appears in owned files, repair with focused tests and one PR. Otherwise report complete evidence without unnecessary code changes.

Forbidden: edit actions.ts, model-provider, extraction/routing, benchmark labels, AGENTS/checkpoint/coordination docs, or shared verify-pipeline script; no live model calls; no Vercel/DNS/account mutation; no OEM-compliance scoring.

## Joint acceptance and review

ARCH reviews both lanes together **after** their evidence/PRs arrive, checks exact source SHA, final required GitHub CI, cross-lane source-to-UI compatibility, row/citation/edit/export correctness and deployment limitations. No green-light if a critical source error, incomplete paid benchmark, missing reviewer path or unsafe client access remains.

Report: final main SHA; PR links/merge state; evidence by score gate; known P0/P1/P2 issues; operator demo steps; credible readiness percentage; explicit next decision. For untested or uncertain aspects state "not verified". No unsupported claims that one successful run proves robustness.

## Shared status at creation

- PRs #386–#389 merged; main 26cc047, required GitHub CI green at previous review.
- Last completed IITG extraction: 192 accepted, 20 known false administrative inclusions, 3 service obligations recovered, 5/7 provisional page-11 groups, 14/16 exact anchors (pre-#387).
- #387 offline classifier replay: 19/20 rejected, 1 review-only; all three service items retained. **Not** fresh end-to-end proof.
- Latest IITG attempt failed after 173.561 s with only 2/4 extraction batches parsed. #388 adds distinct timeout attribution; #389 adds safe physical page IDs. Neither proves a completed post-filter real tender.
- The private local app is the intended near-term pilot. Vercel author access, deployed model secrets, custom domain and hosted OCR are not confirmed ready.

## Final stop rule

Once independent lanes submit results, stop new feature work. ARCH runs one joint review and chooses: (1) ready for operator-led client POC, (2) one narrowly scoped blocker fix, or (3) not ready. Do not launch an unlimited third development wave.
