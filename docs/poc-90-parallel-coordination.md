# POC90: two independent Goal Mode agents + ChatGPT working engineer

**Status:** active client-POC coordination contract, 2026-11-07. This supersedes the earlier three-coding-agent interpretation. The team has **exactly three participants: Agent A, Agent B and ChatGPT**. ChatGPT is an active engineering contributor and integrator, **not a passive reviewer and not a fourth participant**. All three start from the merged main SHA containing this version of the plan.

## 1. Authority, deliverable and score

Read this file, `AGENTS.md`, `docs/checkpoint.md`, `docs/architecture/ADR-0001-document-intelligence-redesign.md` and current open PRs before work. `AGENTS.md` remains the security/PR rulebook, `docs/checkpoint.md` the canonical backlog. This document temporarily overrides historical checkpoint order for this sprint; only ChatGPT updates shared checkpoint status during integration.

Phase 1 product: PDF tender upload -> source-preserving extraction -> technical/supplier obligations -> precise or honestly approximate citations -> human review/edits -> blank OEM compliance/deviation/remarks -> DOCX/XLSX/PDF. **No** OEM-vendor evidence matching, automatic compliance decisions, RAG, multi-tenant architecture, queue/database, new providers or unrelated features. The immediate customer POC is an **operator-led private local pilot**. Remote deployment is an explicit separate acceptance gate.

The previous **70%** is an estimate, not a measured accuracy score. **90% is conditional**, not a promise for end of day. Track potential incremental gains only with evidence:

| Gate | Potential increment | Evidence |
| --- | ---: | --- |
| G1 Real execution | +6 | Historical completed 157.002-second full IITG run on 26cc047 demonstrates one completed flow. Do not silently reuse that success to claim a newly changed version was tested. Confirm final code still passes the scripted pipeline. |
| G2 Precision and source evidence | +7 | Agent A fixes the 12 novel administrative false inclusions + 3 mixed cases without losing technical/service obligations; ChatGPT fixes/dispositions source-reference gaps. Offline replay across saved accepted candidates and adversarial examples, then at most one *separately authorized* final live run after integration. No fabricated source anchors. |
| G3 Client review/export | +5 | Agent B verifies an actual scripted/saved-result user journey, source drawer, checked/edit invalidation, section/row identity and consistent DOCX/XLSX/PDF exports. |
| G4 Operator-led demo | +2 | Agent B provides verified local start/upload/review/export, supported format limits, guarded access and a nonconfidential demo checklist. Hosted domain/Vercel access are separately unverified. |

G2 remains **unproven for unseen tenders** until independently adjudicated evidence; offline tests are not real-model quality results. Don't present 90% as achieved while a P0 is open. One public tender completion is not a generalization metric.

## 2. Latest confirmed evidence — read-only baseline

Main before this coordination correction: `9bfbe7dce648dd16ce822324d66796653f27670e`; no open PRs at inspection. The hash-verified IIT Guwahati 15-page tender uses SHA-256 `88d912e8d3172a99e8422cef2c185dc90692f6b0b1d70e6646f557a524f65967`.

Completed run at `26cc047`: **157.002 seconds, 137,770 provider-reported tokens, 172 accepted rows (146 requirements + 26 section rows), 228 trace candidates reconciled**. 20 previously known administrative cases and four adjacent cases absent, three page-11 AMC/local office/spares obligations accepted. Page-11 evaluator: 14/16 literal anchors matched; source inspection reported 7/7 groups covered semantically (not exhaustive recall). **P0:** 12 other obvious bidder/finance/logistics/tax requirements accepted and three mixed/document clauses accepted without review. **P1:** three page-8 requirements (`req-86`, `req-90`, `req-92`) show empty sourceText, no source element IDs and null offsets though their text was manually seen in the PDF. These may reflect repeated excerpts, mismatched text, or visual/OCR-only evidence; no cause is assumed without the actual artifacts. Partial audit coverage prevents document-wide recall claims.

Ignored local result: `apps/web/.local/benchmark-runs/iitg-20261107T142219Z/`; ignored trace: `apps/web/.local/forensic-traces/`. **Local to the user's Mac** and not guaranteed visible to a different worktree or GitHub. Do not invent inaccessible quotes or pretend to have opened a local private file. All agents may read but not overwrite original evidence.

The existing Vercel author access problem, hosted model secrets, custom-domain DNS and hosted OCR remain deferred for the private local pilot.

## 3. Three-lane ownership and conflict policy

All code contributors work from **the same newly merged coordination SHA** and use **independent worktrees and branches**. Agent A and Agent B each have their own Goal Mode task and branch. ChatGPT performs architecture/code edits through a **separate GitHub PR**, reviews both agents' PRs, and integrates only after required CI passes.

### Agent A — Scope classification (Goal Mode)

- Exclusive code ownership: `apps/web/app/candidate-classification.ts`, `candidate-classification.test.mjs`, newly created `apps/web/app/poc90-scope-*` helpers/tests.
- Objective: diagnose 12 newly accepted administrative cases (req-6/7/8/9/21/25/26/28/29/31/32/33), 3 mixed cases (req-3/5/15), original 20+4 exclusions and the three page-11 service obligations. Use exact available saved source quotes; not descriptions invented as quotes.
- Fix only demonstrably unsafe classification transitions. Mixed cases go to human classification review; technical/supplier performance including genuine delivery of physical equipment, calibration, commissioning, maintenance, training and spares must survive. Evaluate full saved candidate set offline, report changed accepted obligations, new false negative risks, candidate traces.
- No `actions.ts`, source document/provenance, UI/exports or shared docs. At most one focused PR prefixed `[POC90/A]`. No paid live model calls.

### Agent B — Client review and export (Goal Mode)

- Exclusive code ownership: `apps/web/app/tender-mvp.tsx`, `apps/web/app/page.tsx`, `apps/web/app/new/page.tsx`, `globals.css`, `response-sheet.ts`, `response-sections.ts`, `sectioned-exports.ts`, `pdf-export.ts`, `remark-verification.ts` and their matching tests; relevant UI components under `apps/web/components` if required.
- Objective: verify a nonconfidential scripted or saved-completed-result PDF upload -> response sheet -> source drawer (exact vs approximate evidence) -> review/edit invalidation/remove/reset -> DOCX/XLSX/PDF fidelity, source pages, technical units and blank OEM fields. Check desktop/mobile, auth, private local startup, failure paths; deliver a client demo runbook. Do not misstate synthetic replay as real model extraction.
- Use a unique local port such as 3308 if manual browser server necessary. Do not start/stop shared fixed port 3307 via `make pilot-start`/`pilot-stop`. Scripted pipeline uses random ports. No extraction/provider/classification/source helper changes. At most one `[POC90/B]` PR. No paid model calls.

### ChatGPT — Source provenance architecture + code + integration

- **Active code ownership**: `apps/web/app/source-document.ts`, `source-document.test.mjs`, `candidate-evidence.ts`, `candidate-evidence.test.mjs`, `tiered-validation.ts`, `tiered-validation.test.mjs`; `apps/web/app/actions.ts` and shared backend/integration files only when essential and non-overlapping.
- **Active engineering deliverable**: investigate why accepted technical rows can have empty source text/source element IDs/offsets, implement **one small safe source-reference correction** with deterministic tests where code evidence justifies it, preserving exact/approximate distinctions. Report what local IITG artifacts are inaccessible; never invent source evidence. This work is code + PR, not merely documentation or prompts.
- Also owns architecture, shared `AGENTS.md`, `docs/checkpoint.md`, this file, `README.md`, `docs/architecture/*`, `apps/web/scripts/verify-pipeline.mjs` and all unassigned files. Only ChatGPT performs final merge/review decisions.
- ChatGPT does **not** overwrite Agent A's classifier or Agent B's UI/export changes. It does **not** run paid model/PDF/browser tests that require the user's local files; GitHub CI and deterministic tests can validate its own PR.

### Isolation instructions (each agent creates only its own worktree)

```bash
git fetch origin main
git worktree add ../tce-poc90-a -b poc90/a-scope origin/main      # Agent A only
git worktree add ../tce-poc90-b -b poc90/b-client origin/main     # Agent B only
```
Do not run both commands as one agent. Check existing worktrees/branches first; never delete/overwrite work. Agent A and B may be executing simultaneously; each has its own `node_modules`, `.next` outputs, processes and `.local` records. ChatGPT's GitHub PR is a separate branch on the remote.

**Forbidden to all:** editing another lane's paths; modifying shared docs in agent PRs; changing unmerged other-lane branches; altering golden evidence to make tests pass; committing private tender/model data or credentials; making a paid live model call; retries or unbounded experiments; multi-PR chains; deploying or mutating Vercel/DNS/secrets; auto-merging. If a fix needs a different lane's code, report a handoff with exact file, desired interface, regression and rationale; continue only independent work.

An agent that discovers no justified code change should report evidence without opening an artificial PR. One focused PR per agent maximum. Required GitHub `web` CI must pass on the head SHA; Vercel author-permission errors are separate and do not excuse failed required CI.

## 4. Shared verification and handoff

Each coding agent runs, if supported and isolated:
- `npm --prefix apps/web test`
- `npm --prefix apps/web run typecheck`
- `npm --prefix apps/web run build`
- `npm --prefix apps/web run test:pipeline`
- `git diff --check`

Agent B additionally provides browser/UI/export evidence and private demo instructions. ChatGPT's source-reference code requires synthetic regression checks and required GitHub CI before merge. If a check is unavailable, say **SKIPPED**, not PASS.

Every handoff must contain:
```text
LANE: A / B / ChatGPT
BASE SHA:
HEAD SHA:
PR LINK OR NONE:
OWNED FILES CHANGED:
EVIDENCE USED (saved/synthetic/browser/direct PDF):
TESTS (pass/fail/skipped):
ACCEPTANCE GATES (pass/fail/unverified):
REGRESSIONS/TRADEOFFS:
P0/P1/P2 ISSUES:
CROSS-LANE INTERFACE REQUESTS:
LIVE MODEL REQUESTS: 0
READY FOR INTEGRATION: yes/no
```

## 5. Integration and stop rule

ChatGPT may ship its **independent source-provenance PR while the two agents work**, after checking file ownership. Once both agents finish, ChatGPT reviews all three changes, merges sequentially with SHA-guarded required CI, checks final main CI/contract, and updates canonical checkpoints in one integration/docs PR. No automatic source-gold re-labeling.

Then decide whether exactly **one explicitly approved** controlled final paid benchmark is justified on the final merged SHA. If the model fails, preserve error and no false quality claim. Final response: merged SHAs, verified evidence by gate, current readiness estimate, critical blockers, demo procedure, next recommendation. Stop after one three-lane cycle: (1) private pilot ready, (2) one targeted remaining blocker, or (3) not ready. The target is speed **without** accepting invented citations or unreviewed supplier claims.
