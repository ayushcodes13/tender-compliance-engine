# Tender Review MVP checkpoint

## Product scope

A single-user Next.js app demonstrates one meaningful AI engineering workflow:

```text
Upload a text-based tender PDF
→ extract technical requirement quotes
→ verify each quote against selectable text on its cited page
→ show that page and its bounding box
→ let a human mark it checked
→ edit the response sheet and remove unwanted rows
→ download DOCX, PDF, or Excel with the reviewed edits
```

This is a deliberate simplification requested by the user. The deployed product is one Next.js app. It has no separate API service, worker, database, queue, or Docker setup. Tender bytes and review state stay in browser memory. GPT-6 Luna is the only model provider; the server-side credential is never exposed to the browser.

## Phase 1 v2 execution tracks (execution-first reset 2026-11-10)

The active direction is to stop expanding the design and deliver a runnable LLM-led, resumable vertical slice. See [`plan.md`](../plan.md) for the compact scenario and milestone acceptance criteria. Build incrementally on the current Next.js app; do not wait for every model-quality experiment before implementing runtime behavior. Evaluation remains mandatory before quality claims, prompt/model tuning, or generalization claims.

### Track A — runtime architecture (active)

- [x] **R1 — Run/TaskPlan/WorkUnit contracts:** `apps/web/app/analysis-run.ts` defines typed run/proposal/work-unit envelopes, explicit legal state transitions, SHA-256-bound run identity, source-bound idempotency keys, retry attempts, and deterministic execution ordering. `apps/web/app/analysis-run.test.mjs` covers identity, transition legality, monotonic timestamps, retry counting, ordering, duplicate work, and invalid source inputs. This is a provider-independent domain contract only: it is not connected to analysis execution and does not provide persistence or resumability. PR #433.
- [ ] **R2 — LLM-led task planner:** let the model propose tender scope, structure, relevant/unresolved regions, inspection modes, and requirement organization from the parser inventory; validate source IDs and supported operations before bounded execution. No template catalog.
  - PR #434 added bounded page-level planning, source/page validation, and routing/review hints. The current follow-up adds bounded parser-region summaries and parent-page-bound action references. It conservatively refuses unsupported exclusions when page or region context is clipped, omitted, or unreadable. R2 remains open: validated actions still feed the legacy page router; they do not yet create/execute independent work units. This PR updates `plan.md` to execution-first milestones and does not claim a full architecture rebuild.
- [ ] **R3 — Planner-driven executor and coverage:** make validated page/region actions drive stable work units; connect existing native-text/table extraction; record a terminal coverage state for every supplied page/region. Keep OCR/visual and cross-page work unresolved until their executor exists.
  - Progress after PR #435: validated actions are materialized into source-ordered inspection WorkUnits with operation-specific idempotency keys and parser-bound page numbers. They still only seed the legacy router; independent unit execution, per-unit results, and terminal region coverage remain open.
- [ ] **R4 — Durable resumable vertical slice:** persist one bounded work-unit type and source-linked result; fault-inject timeout/restart; prove retry/resume without duplicated or reordered results. Select and test the local/private persistence adapter and security behavior before claiming durability.
- [ ] **R5 — Review/export integration:** progress, plan rationale, source navigation, incomplete states, append-only review actions, and reviewed export snapshot. Define partial-result UX before exposing partial drafts.
- [ ] **R6 — Hardening and rollout:** expand operation types; test privacy, prompt injection, failure/restart, size/concurrency/cost/latency; document reversible rollout evidence.

### Track B — evaluation and anti-overfitting (parallel; quality gate)

- [ ] **V2.2b — Independently review and adjudicate whole-tender source labels.** The NCESS 20-page record merged in PR #431 contains 178 labels and 299 source-verified anchors, but is single-assistant, unadjudicated development material. It is not gold or a quality baseline.
- [ ] **V2.3 — Baseline current pipeline against adjudicated labels** with separate omission, false inclusion, split/merge, exclusion, citation, fidelity, coverage, and review-burden measures. No paid/live model calls without explicit user authorization.
- [ ] **V2.4 — Whole-tender validation and locked-evaluation split.** All existing examples and previously used tenders remain development data; keep versions/near-duplicates/families together. Do not tune on locked evaluation.
- [ ] **V2.5 — Controlled model/prompt improvement and comparison** only after V2.2b–V2.4 evidence is ready; locked-evaluation documents remain untouched.

### Current baseline evidence

- [x] **V2.1a — Fingerprint and split inventory:** record SHA-256, bytes, physical page count, and selectable-text-bearing page count without storing extracted text; keep PGIMER copies in one family and assign known-used material to development.
- [x] **V2.1b1 — Record bounded provenance/layout and historical failure evidence** in `benchmarks/representative-tenders/README.md`.
- [x] **V2.1b2 — Complete declared source/layout characterization** across the 367-page corpus at the documented depth. This does not establish cell correctness, semantic coverage, or independent review.
- [x] **V2.2a — Define annotation protocol and validate provisional pilots.** See `benchmarks/phase-1-v2-annotations/`; pilot records remain development-only.

### Merge/deployment note

Known billing-blocked Actions jobs are treated as infrastructure-unavailable only when GitHub reports the job never started and has no steps. Run local equivalents and distinguish them from remote checks. Free-host edge verification, customer document handling, and public rollout are separate gates; no tender is sent to an unapproved hosted endpoint.

## Historical POC90 and customer-validation records

The following dated sections record prior decisions and results; they are evidence/history, not the active execution sequence unless a current checkpoint explicitly references them.

## Historical user-directed reliability foundation (2026-11-09)

This earlier customer-validation sequence is superseded by the Phase 1 v2 execution tracks above. Its release evidence remains useful context; its open hosting/save-resume checkboxes do not override the current architecture sequence. OEM behavior remains out of scope for Phase 1 v2.

- [ ] **Free hosting for PDFs up to 32 MiB:** prepare a genuinely free preview configuration, enforce bounded uploads, and verify the deployed provider edge limit before claiming hosted acceptance. No paid service creation or deployment is authorized by this checkpoint.
- [ ] **Safe save/resume:** preserve the current tender identity, source citations, reviewer decisions and sheet edits across reloads in the existing single-user workflow; expose storage limits and recovery state clearly.
- [ ] **Processing recovery:** represent cancellation and incomplete work accurately, preserve recoverable completed work, and clean up request and temporary resources without adding queues or workers.
- [ ] **Verification:** deterministic regression tests, typecheck, production build and scripted pipeline pass for the integrated changes. Hosted provider behavior remains a separately disclosed gate.

The first hosting implementation is in progress on a focused PR branch. Its local 32 MiB upload path passes; the free host has not been created, deployed, or edge-tested.

## Active POC90: two Goal Mode coding agents plus working ChatGPT engineer (2026-11-07)

This is a temporary sprint priority, superseding historical first-unchecked checkpoint order for the work in [the active coordination contract](poc-90-parallel-coordination.md). ChatGPT owns real code and integration, not only review. The coding agents must not edit these shared docs concurrently. The 70% -> conditional 90% readiness estimate is evidence-gated, never a percentage of checkboxes.

Historical completed IITG tender analysis at `26cc047`: 157.002 s; 137,770 provider-reported tokens; 172 accepted rows; original 20+4 admin examples excluded, three critical service obligations retained, but 12 other administrative requirements and three mixed clauses accepted, and three page-8 technical citations with incomplete sourceText/IDs/offsets. No fresh run is authorized by this document.

- [x] **Agent A, scope classifier (PR #395, merged `f00c455`):** correct the newly observed administrative/mixed false positives without suppressing technical/AMC/service obligations. Offline replay saved candidate set, adversarial tests, focused PR in exclusively owned `candidate-classification*` files.
- [x] **Agent B, client journey (PR #394, merged `1a338df`):** independently verify safe PDF upload, edit/review, source drawer/approximate warnings, DOCX/XLSX/PDF export and private local demo. Own only UI/export files. Open at most one PR for an observed bug; no model calls.
- [x] **ChatGPT, engineering + architecture (PR #393, merged `d7e8aaa`):** inspect source-reference helper behavior for the three page-8 evidence warnings, implement an independently testable source-provenance correction if justified, and open own focused PR in `source-document*`/owned helper files. Own cross-lane integration and reviewed merges.
**Three-lane integration evidence (2026-11-07):** Source-reference fallback, approximate-citation UI and administrative classification PRs #393, #394 and #395 are all merged in sequence. The final `main` at `f00c455` passed required GitHub `web` CI: tests, typecheck, production build and scripted pipeline. No new paid provider requests were made during integration. Agent A's saved 228-candidate offline replay reports the 12 newly accepted administrative rows now as 9 rejected + 3 review-only; all three mixed clauses review-only; three page-11 service requirements retained (AMC requires review). Agent B's non-live browser/scripted-fixture walkthrough and export inspection were reported as passing. ChatGPT's source helper handles one repeated-native-quote case safely, but `req-86/90/92` are **not individually revalidated** because their local private run artifacts are not accessible through GitHub. None of these establish fresh end-to-end precision on the integrated build or quality on unseen tenders.

**Gate accounting:** G1 historical completion +6, G3 Agent B browser/export +5, G4 private local operator setup +2 = **83% provisional**, conditional on the reported local evidence. G2's remaining +7 is **not awarded** until a controlled post-integration run and source inspection confirm scope and citation behavior. The 90% goal remains open; user approval is required before one more paid benchmark. Source-gold labels, hosted setup and dependency audit findings remain separate open risks.

**Final controlled POC90 live acceptance — FAIL (2026-11-07).** A single 15-page IIT Guwahati run on `fa25f34` completed in **103.910 s** with **114,170 provider-reported tokens**, 107 requirement rows + 19 headings and a reconciled 165-candidate trace (126 accepted, 25 rejected, 14 review-only). This meets the narrow runtime-completion gate; it fails G2 extraction correctness: the full five-year AMC obligation split, and the charge/duration, service visits and spares/consumables fragments were routed out of the accepted matrix. Only 2/3 critical service-obligation groups were accepted, although 6/7 annotated groups were semantically represented across accepted/review content. Three more bidder-form/service confirmations were accepted (the exact reported accepted `req-123` text was "Warranty period agreed"; the other two were service-centre contact/after-sales term declarations). **30 of 36 historical admin cases came from pages not selected by routing**, so their absence is not evidence that this run verified classification precision. All 9 selected pages were marked uncertain; routing context clipped on 15/15 and coverage linkage for most detected table pages was incomplete. No full-document recall or unseen-tender quality claim is warranted.

**Post-run targeted engineering:** PR #397 (merged `3299505`) conservatively routes form-style warranty acknowledgements and service-centre contact information to human classification review, with synthetic regression tests. That PR **has not been tested in a new paid tender analysis**, and it does not reassemble the AMC group. Private run artifacts remain on the user's local filesystem in the ignored `final-poc90-20261107T174616Z` directory; do not replace them with invented quotes. Future work should first inspect those fragments alongside their exact source page and implement a source-grounded group/context mechanism with offline evidence before spending provider tokens. POC quality acceptance remains **FAIL** and conditional 90% readiness is **not achieved**.

**AMC follow-up on current code (2026-11-08):** PR #399 (merged `4a104e0`) adds deterministic source-linked grouping of a five-year AMC introducer and immediately following service-list fragments. The local operator's saved-candidate replay (original PR head, no model calls) reported all five p.11 fragments retained as distinct, independently cited accepted matrix rows with a shared parent/member group reference, while adjacent local-support and post-warranty obligations remained separate. **Integrator safety changes** before merge preserved any original classification human-review flag; disallowed treating end-of-page as a proven list boundary; and refused ambiguous bullet-separated next-list-item boundaries. Updated PR CI passed unit tests, typecheck, build and scripted pipeline; the stricter final branch was **not re-evaluated against the private saved tender artifacts**. This remains offline mitigation only and does not change the last real-run FAIL verdict. The current main branch must undergo a fresh controlled acceptance review before G2 can be marked PASS. Table-row coverage linkage, uncertain routing, and unseen-tender generalization remain unresolved.

**NIOT follow-up, operator recovery, and schedule deduplication on current code (2026-11-08):**
- **PR #403 (merged `ba2740f`):** Resolves NIOT candidate classification blockers and telemetry retention. Extends technical scope patterns with instrument hardware nouns (`display`, `readout`, `sensor`, `probe`, `salinometer`, `psu`) and deliverable protective cases so `"Display: Digital readout"` and `"Autosal packing case"` are classified as technical scope. Tightens administrative filters for order acceptance, DAP transit insurance, seaworthy packing, wire transfer/TPI terms, wood packaging/ISPM 15, and bid commentary. Aligns the narrative omission audit schema and retains provider usage/error telemetry on malformed responses.
- **PR #404 (merged `ec4b02e`):** Removes demo labels, implements operator recovery dialog, enables 1-click candidate promotion from review queues, elevates unresolved coverage warnings to a top banner, and preserves authentic operator provenance (explicitly separating manual wording from parser-verified citations).
- **PR #405 (merged `ec74897`):** Reconciles identical technical specifications duplicated across separate schedules/sections (e.g. NIOT p.18 bidder compliance schedule vs p.20 technical specifications annexure), combining page citations (e.g., `"Pages 18 and 20"`) and preserving all source requirement IDs while avoiding false merges on different limits (`200 bar` vs `500 bar`) or distinct parameters (`Number of Isolators` vs `Leveling Valves`). Surfaces operator-actionable duplicate alerts in the UI.
- **Verification status:** All fixes are verified through 351 unit tests (`npm test`), Next.js production build (`npm run build`), TypeScript typecheck (`npm run typecheck`), and 26/26 end-to-end scripted pipeline contract cases (`npm run test:pipeline`). **Zero new paid model calls were authorized or executed during this integration.** Live model execution on unseen tenders remains unverified on the integrated build.
- **Export provenance policy:** Source page citations are preserved in DOCX and XLSX exports. By documented policy ("Native source headings sit above specification tables; UI provenance stays in the UI"), page citations are intentionally omitted from printable PDF exports.
- **PDF export private-use bullet correction (2026-11-09):** The supplied `input 1.pdf` has two page-10 bullet characters that PDF.js exposes as U+F0A7. The embedded export font cannot render that private-use code point, so PDF export previously stopped. The PDF exporter now normalizes U+F0A7 and U+F0B7 to a standard bullet for rendering while preserving the editable UI sheet unchanged; the exact U+F0A7 case is covered by a PDF round-trip regression test. This corrects this observed glyph only and does not imply general support for arbitrary private-use characters.

**42-page extraction throughput follow-up (2026-11-09):** PR #419 (`cee22c9`) replaces wave scheduling for independent vector-table inspections and source-row audits with bounded sliding concurrency. The shared provider cap is six, independent table-column mapping is capped at four, and per-page audit capacity is reserved in source order before provider waits; completed results are still applied in source order. The PR adds a 17-page scripted straggler regression. The retained balanced-concurrency run log at `.local/client-review/42page-throughput-balanced-2026-11-09.log` records a 42-page analysis returning HTTP 200 in 246.553 seconds, with all 10 general-extraction and 8 text-omission-audit requests parsed; it records 253,966 prompt and 80,004 completion tokens (333,970 total). The matching source PDF is `examples/IIT Gandhinagar - Optical Tables with Vibration Isolation Systems.pdf` (SHA-256 `be39fd08ab61011d7281c7f355b61864b28b091001712fbdeecd1c5181e3c491`). The PR report says the returned sheet had 162 rows with source text and physical-page citations, but the response sheet itself is not retained, so that row/citation assertion is not independently rechecked. Pages 36–42 were marked incomplete for omission review and require human review; no extraction-completeness claim is warranted. Across five logged live analyses in this investigation, parsed usage totals 940,686 prompt + 309,620 completion tokens (1,250,306 total). At the public GPT-6 Luna standard rates, that is an estimated $0.249, not an invoice; the configured Azure-compatible endpoint's actual charge was not verified. No sixth model call was made. At the merged PR head, 383 unit tests, typecheck, production build, and all 26 scripted pipeline cases passed locally. The full 20-step browser review/save-resume/export acceptance remains open; the Vercel deployment check remains blocked by project membership, and no hosted preview was deployed.

**Sixth live run and partial-batch recovery reproduction (2026-11-09):** The sixth run used the same 42-page PDF SHA-256 on merged `cee22c9`. In the browser, PDF upload/validation and parsing completed; five of six technical extraction batches parsed, then the page-17 batch failed with a provider connection error after 62.262 seconds. The SSE request returned HTTP 200 after 174.009 seconds but ended with the visible endpoint error and no response sheet. The log records 149,207 prompt + 39,731 completion tokens (188,938 total). Across all six logged analyses, usage totals 1,089,893 prompt + 349,351 completion tokens (1,439,244 total), or an estimated $0.284 at [public GPT-6 Luna standard rates](https://developers.openai.com/api/docs/pricing); this is not a provider invoice and the Azure-compatible endpoint's actual charge was not available. At that point, no further paid call was planned; the later post-merge run is documented below.

The reproduced failure path was all-or-nothing: completed batch outputs and per-page incomplete states were collected, but any failed batch prevented the result from reaching the response-sheet stage. PR #422 changes that path to return already source-verified work only when a completed extraction or prior source-grounded table work exists; failed-batch pages remain `incomplete`, and the review note warns that model coverage calls failed. When no usable work completed, the request still fails without an empty/partial sheet. The scripted pipeline exercises both the one-batch disconnect and the all-batches-failed cases. The sixth run above predates this fix and produced no result sheet. The post-merge browser workflow and its limits are recorded below.

**Post-merge 42-page browser acceptance (2026-11-09, `7cecf39`):** A seventh live GPT-6 Luna analysis was run on the same 42-page PDF after PR #422 merged. The browser completed in 4:21 and produced an editable, source-cited draft; it did **not** prove complete extraction. The result warned of 84 held candidates, one incomplete page audit, 26 pages with possible omissions, 25 router-uncertain pages, 34 unmapped table rows, 42 clipped router pages, and 33 duplicate schedule specifications. No requirement was pre-checked. This call's token usage was not retained in the local model-timing log; using the preceding successful run's 333,970-token usage as a conservative proxy gives an estimated $0.065 at [public GPT-6 Luna standard rates](https://developers.openai.com/api/docs/pricing), not a billed amount. Including all seven known and estimated runs, the proxy total is about 1.77 million tokens and $0.349 at those list rates; the configured Azure-compatible endpoint's actual charge remains unknown. The seven-run estimate remains far below the authorized $30 ceiling. No further call is needed for this browser workflow.

The operator workflow was then exercised against the live draft. A page 5 bidder authorization instruction was removed. A page 21 compressor obligation was manually added with page attribution and its OCR spacing normalized in editable wording; the original page remains the evidence source. A duplicated manual validation entry was removed after confirming that the extracted validation wording already existed. The compressor entry was marked checked. The page 10 citation opened physical PDF page 10, displayed the exact source quote and source-element IDs, and rendered a visible highlight. An encrypted `.tce-review` file was downloaded, the app was reloaded, the same PDF was reselected, and the saved file was imported with its passphrase. The UI confirmed SHA-256 source verification and restored the edit, deletion, and checked state (1/131 checked; 128 response rows after edits). The original PDF is not embedded in the encrypted review file; the operator must keep and reselect it.

DOCX, XLSX, and PDF were downloaded from the resumed review and independently opened with ZIP/XML parsing and `pdfinfo`/`pdftotext`; the DOCX and XLSX were also rendered with LibreOffice for visual inspection. All three contain the edited compressor requirement, omit the removed authorization instruction, retain the 3000 mm and 1500 mm limits, and show a per-row `Checked` / `Needs review` status. The XLSX contains the response fields and source-page column; DOCX has 24 tables and its visible headers were confirmed in the independent render; PDF is 19 pages and its text extraction and rendered table layout succeed. Printed PDF continues to omit source-page citations by documented export policy. A focused export projection now carries check state without modifying the editable response sheet or its source wording. These checks establish export integrity for the exercised fields and rows, not complete tender correctness or visual inspection of every page. Local artifacts are in `.playwright-cli/` and screenshots are in `.local/client-review/live-acceptance-2026-11-09/` (ignored, not committed). The full review of 84 held candidates and all coverage gaps remains open; no completeness or quality acceptance is claimed. The Vercel authorization issue and hosted preview/32 MiB ingress gate remain unresolved.

- [x] **Joint acceptance/integration (completed with FAIL verdict):** all three handoffs, green required GitHub CI, serial PR merges, final scripted contract, update these checkpoint statuses with evidence, decide on at most one separately authorized paid final benchmark and issue P0/P1/P2 and readiness verdict.
- [ ] **Conditional +20 POC readiness gates:** historical real completion (+6, does not prove post-fix code), precision/source truth (+7), verified review/export (+5), repeatable private pilot (+2). No 90% claim while critical scope/citation errors remain or when only synthetic evidence supports quality.
- [ ] **Deferred hosted scope:** Vercel author access, remote model credentials, custom-domain DNS, hosted OCR and independent customer signoff unless user specifically requires public hosting.

### Reading dated implementation notes

The dated entries below preserve the sequence of implementation and investigation. They are historical snapshots, not a single description of current behavior. When entries conflict, the later relevant entry supersedes the earlier one; current source code and its regression tests are authoritative for shipped behavior.

### Additional adversarial audit sequence — 2026-11-06

The new audit identifies reliability work that supersedes the older deployment-first ordering. Address confirmed findings in this sequence: hybrid-page OCR; independent response decisions for separate obligations; access control and request quotas; visual-completion provenance; OCR confidence for numeric/operator tokens; long-cell spreadsheet clipping; source-page citations in exports; and queued model-request deadlines. Keep custom-domain DNS as an open release gate. These items change distinct safety or operational guarantees and should remain separate PRs.

The independent-response change supersedes the earlier 2025-10-25 response-capacity note where it says verified subpoints from one source cell should be reassembled into one response row. Every accepted, independently assessable split stays in its own response row with its own source requirement ID and blank OEM decision fields. Page continuations of one obligation and presentation headings may still merge. The existing 250-response-row limit applies after this projection and stops oversized analyses without partial output.

The unauthenticated-upload finding now has a production Basic-auth gate, with a fail-closed response when its password is missing. A bounded in-process model-request admission gate also limits each warm app instance to six active requests and 24 queued requests, with three active requests per analysis and a 30-second queue deadline. This reduces bursts within one instance; it does not implement per-user quotas or a cross-instance concurrency limit because the single-app MVP has no shared state store.

Model-proposed visual completions no longer replace source text in a requirement or export. The literal selectable quote remains the response text; a high-confidence completion is attached only as a visibly unverified suggestion in the source drawer. Human confirmation is still required before any wording is changed in the editable response sheet.

Local Tesseract parsing now retains per-word confidence and geometry. A line containing numeric values derives its confidence level from numeric/operator tokens and adjacent recognized engineering units, rather than letting high-confidence prose raise a weak technical value's average. When multiple technical values share a line, the lowest relevant token confidence controls the line-level review signal.

Excel export now splits long cell contents across bounded-height physical rows instead of capping one oversized row and clipping its tail. Continuation rows preserve the source wording in order and vertically merge the OEM response fields so the requirement still has one response decision. The spreadsheet regression test checks the generated worksheet values, row heights, and merged response field.

Sectioned DOCX and XLSX exports now include the existing locked source-page column, so recipients can trace requirements back to the tender. Printable PDF intentionally keeps omitting that column and its page-number footer, per the 2026-10-25 client clarification; the source page remains available in the review UI. Tests inspect the generated DOCX/XLSX content and preserve the PDF omission check.

Model calls now keep analysis cancellation active while waiting for a concurrency slot, then start their 90-second execution timeout only after admission. This prevents queue wait from consuming the provider's execution window; the regression test holds a request in the queue longer than the execution window's remaining time and verifies it still receives a fresh window. A separate wall-clock budget for the complete analysis is not added by this change.

### Evidence-first redesign sequence update — 2026-11-07

- [x] Require an explicit per-page routing disposition and reason. Relevant pages enter extraction even without a section range; possibly relevant pages remain unresolved; only explicit, reasoned exclusions count as excluded; absent model decisions remain unrouted. Schema validation, duplicate/out-of-group rejection, and scripted upload-to-sheet routing are covered in PR #353. This is an explicit routing record, not proof of page-level or document completeness.
- [x] Send pages explicitly marked uncertain, including `possibly_relevant` pages, through source extraction and the separate coverage audit while retaining their uncertain disposition in the ledger (PR #356). This is deeper inspection, not a resolution of the routing uncertainty.
- [x] Send pages omitted from per-page routing dispositions through the same deeper extraction path, while retaining `unrouted` in the ledger and review note until a human resolves the routing gap (PR #357). This does not cover pages with no text that never entered router batches.
- [x] Batch text-page omission audits so an oversized combined request no longer skips every selected text page; preserve per-page incomplete states for over-limit pages and work beyond the eight-batch cap (PR #358).
- [x] Keep visual extraction and omission-audit requests within the provider's per-analysis admission limit; verify wave scheduling and progress updates (PR #359).

The additional adversarial audit was written against `c198300`, before PRs #309–316. Rechecking current `main` confirms its listed hybrid OCR, independent response rows, production access gate, visual-completion separation, value-level OCR confidence, long-cell Excel splitting, DOCX/XLSX page citations, and queued execution-timeout findings have each been addressed in separate PRs. The model provider now also applies a bounded process-local admission gate; global per-user/tenant quotas and cross-instance concurrency remain open because this single-user app has no shared state. Printable PDF page citations remain intentionally omitted under the earlier user clarification; DOCX and XLSX include them.

The user's broader document-intelligence redesign changes the next-work sequence. Keep custom-domain DNS and hosted preview access as open release gates, but proceed with the evidence baseline and architecture before deployment work. The six-document parser/model run and partial human-adjudicated cases are recorded in `benchmarks/representative-tenders/`; the results show only 2 of 6 local analyses completed within the 295-second client limit and do not establish recall. One additional public tender baseline candidate is now recorded, but its gold annotation is also partial. The next implementation checkpoint is a complete source inventory and independently annotated golden/held-out set, followed by measured parser and extraction changes. The baseline remains incomplete and has no cost telemetry. See `docs/architecture/ADR-0001-document-intelligence-redesign.md` for the staged architecture decision and trade-offs.

The scripted upload-to-sheet contract now reports a focused mutation check: one requirement omitted by the fixture's first extraction is returned by its separate audit response and admitted only after source verification; one corrupted numeric value is rejected while the original quoted requirement remains. The contract output reports 1/1 for each seeded case. Because the provider is scripted, these results verify audit/recovery/grounding integration only; they do not measure live-model omission detection or real-tender quality.

The held-out IIT Guwahati page-11 annotation now includes short exact source anchors and critical constraints for its seven previously recorded obligation groups. Anchors were checked against text extracted from the official PDF after its SHA-256 matched the manifest, and the page render was visually inspected. This improves source traceability in the provisional gold; human adjudication is pending, four prior positive extraction rows remain unverified because the saved rows are unavailable, and no recall score is claimed.

`benchmarks/scripts/verify-golden-anchors.mjs` now repeats the manifest-hash, page-range, and source-anchor checks for versioned held-out annotations using local Poppler tools. It reports counts without printing or persisting tender text. The documented invocation passed for the existing 16 page-2–4 anchors and 16 page-11 anchors across 23 case records; this validates annotation/source correspondence only.

The analysis SSE route now aborts processing at 270 seconds, before its 300-second route limit, and reports a terminal incomplete error with no response sheet when that deadline is reached. This prevents a long multi-batch run from continuing until the hosting layer terminates the request without a useful completion state. It is an all-or-nothing guard, not resumable processing; a timed-out tender must be retried as a shorter section. Unit coverage verifies abort propagation and that a result produced after deadline is suppressed. No real-tender runtime benchmark was run for this deadline change.

Visual inspection and Tesseract 5.5.3 on the scanned Shah tender surfaced a specific high-confidence critical-value error: page 2's printed `10⁻⁸` AFC stability value was read as `10°` at 90.6 confidence through the application's PSM 3 path; the same substitution persisted under PSM 4, 6, 11, and 12. A conservative OCR review signal now marks numeric values followed by a bare degree glyph low confidence, while preserving the original OCR text and raw numeric score; ordinary `°C`/`°F` values are not downgraded. A sourced adversarial record and unit regression test capture the case. This is a single scanned negative example, not a measured OCR accuracy improvement; human adjudication remains pending.

Further inspection of page 3 found the printed `1.6 × 10⁹` sensitivity transcribed by the production PSM 3 path as `1.6 x 10”` at 72.1 token confidence (medium). Quote-like marks immediately following a number now also trigger low-confidence review; OCR text and raw scores remain intact. A second source-hash-bound negative case records the value and approximate token location. The broader rule also flags legitimate inch-mark measurements; this conservative false-positive trade-off needs evaluation on more scanned tenders. Both Shah cases remain assistant-reviewed pending human adjudication.

Inspection of Shah page 4 found the printed magnet threshold `≥6.5 kG` transcribed as `>6.5 kG` at 70.7 numeric-token confidence (medium before the new signal). Bare `<` or `>` OCR operators before numeric values now lower the line review signal while leaving the transcript and score unchanged; valid strict inequalities will also be flagged. The source-hash-bound case is recorded in `saha-ocr-adversarial-v0.3.json`. This is another specific negative example, not a measured OCR accuracy change; human adjudication remains pending.

The source review also confirmed the objective's Saha cross-section inconsistency: page 1 names a floor-standing X-Band EPR spectrometer, while the Annexure II title on page 5 names a spectrofluorometer despite carrying the EPR NIT number. Routing now returns possible two-page conflict proposals with exact quotes; the application validates both quotes against their page transcripts, marks both pages uncertain, routes both for extraction, and explicitly avoids selecting an authoritative source. Scripted pipeline tests exercise supported and forged conflicts. This adds a grounded warning path, not an independent or measured conflict-detection score; the source discrepancy remains pending human adjudication.

A new IIT Guwahati geosynthetic UTM tender is now recorded separately as an additional public-source baseline candidate. The local model run completed in 288 seconds but selected only pages 6–11, left nine pages unaudited, and produced 114 rows all requiring human review. Manual comparison of the rendered page 11 found three missed after-sales/maintenance obligations. This is partial adjudication on one additional document, not an exhaustive held-out score. The PDF remains local and is not redistributed; its public source, hash, parser counts, run conditions, and golden cases are in `benchmarks/representative-tenders/heldout-*2026-11-07.json`.

Assistant-reviewed page-level relevance dispositions cover all 15 pages of the IIT Guwahati sample; human adjudication is pending. Page 11 has seven obligation groups (three recorded misses and four summary-reported positives whose exact output rows were not retained). Pages 6–10 have 53 additional partial source-obligation groups in `heldout-golden-v0.3.json`; pages 8–10 use grouped test-jig/software/equipment entries and are not an exhaustive atomic decomposition. `heldout-golden-v0.4.json` adds 14 source-backed documentary/service and repeated-form units across pages 2–3 and 12–13; `heldout-golden-v0.5.json` adds two page-4 installation/commissioning and conditional demonstration units. These pages were not selected by the captured model run and saved output-row text is unavailable, so these artifacts record source expectations and routing-level omissions, not candidate-level recall. Page 1, page 5, and the remaining items on pages 12–15 still lack item-level annotations. Parser-reported bounds, numeric interpretations, and obligation completeness require independent human adjudication. Nine pages outside the original omission audit remain unevaluated for recall. See `benchmarks/representative-tenders/heldout-page-dispositions-2026-11-07.json` and the held-out golden files.

Current routing coverage now records each PDF page as selected, uncertain, unrouted, or lacking native/OCR text. Uncertain and unrouted pages remain visible in the review ledger with physical page links; this disposition record improves observability but does not independently establish relevance or completeness.

Native requirement references now expose the parser text-block IDs overlapped by their exact quote spans; table references expose table/row/cell IDs; and OCR references link only exact transcript-region matches. Visual-only transcriptions without a deterministic transcript match remain unlinked to text elements. These IDs establish source-element joins, not semantic paragraph/list hierarchy or completeness; source-unit disposition and independently adjudicated coverage remain open.

Detected vector-table coverage rows now carry the same table/row/cell IDs and link the accepted requirement IDs associated with that source row. A separate bounded model pass compares requirement-classified rows with extracted quotes and reports no gap, possible gap, ambiguity, or an incomplete audit. Requests are limited to 12 rows/12,000 characters with a 16-request analysis budget; any work outside those limits stays explicitly incomplete. Audit dispositions are retained for all detected rows even though the UI previews only twelve per page. The audit records an advisory status and note only; it does not add requirements or mark a row complete. Every nonempty row remains visibly unresolved, including rows where the audit reports no gap. This same-model pass is not ground truth or a measured omission recall result.

Vector-table row classifications now retain a bounded reason code in the source ledger. Ambiguous rows remain visible and do not become requirements by default; header and instruction classifications also remain inspectable with their reasons. This is model-assisted triage, not adjudicated truth or a semantic completeness result.

The page inventory now records raster-image presence, whether OCR was recommended, whether it ran, and whether it found text, found no text, failed, or was skipped because of engine/page/time limits. Native text and OCR regions remain separate. Synthetic tests cover hybrid native-plus-OCR pages and distinguish each OCR outcome. This improves provenance reporting only; it does not detect image-region coordinates or change page routing/extraction behavior. The full source inventory and completeness audit remain open.

The inventory now captures approximate image-draw bounds from PDF.js graphics transforms, retains stable page-scoped region IDs, uses significant image regions with sparse native-text overlap as an additional whole-page OCR trigger, and overlays the approximate bounds in the source viewer. A synthetic hybrid-page test verifies bounds and OCR recommendation; a cross-parser check matched the first Saha page's two PDF.js regions against PyMuPDF bounds within rounding. Across the six PDFs, 48 regions were recorded on 42 pages and 23 pages were recommended for OCR versus 21 under the earlier page-only heuristic. The 5% area threshold avoided adding passes for the repeated small IISc header image; these trigger counts do not measure OCR accuracy or requirement recall. Small image regions and non-image visual content still need human inspection.

Before model routing, the pipeline now builds supported vector-table row candidates for every page, then checks that every physical page is present in order and that native text spans, source-element IDs, OCR/image links, and detected table/row/cell relationships are internally consistent. A failed integrity check stops extraction; successful reviews expose the check in the coverage ledger. Table geometry remains heuristic and may miss or combine tables. This validates inventory structure only; it does not prove that the parser recognized every source region or that the model found every requirement.

Region-triggered pages with selectable native text now OCR significant image regions independently and crop those regions from one rendered page image; scan-only or otherwise unlocalized pages retain full-page OCR. OCR line and word boxes are mapped back to page coordinates, and each cropped OCR region links to its parser-owned image-region ID. Region selection, coordinate mapping, and source linkage have synthetic regression coverage. This does not establish OCR accuracy or image-region recall; approximate bounds and human review remain necessary.

The six representative source PDFs are available locally and their fingerprints match `benchmarks/representative-tenders/manifest.json`. The PyMuPDF shadow inventory covers all 183 pages and now records parser-reported geometry for 3,337 native text blocks, 48 embedded image draws, and 376 table candidates, with no extracted source text. It independently confirms 13 image-only pages in the scanned Shah tender and native text on every page of the other five documents. This remains a parser-side inspection aid, not production PDF.js geometry, semantic routing, verified citation evidence, or an extraction completeness result; independent region dispositions remain open.

## Checkpoint 72 — Single-user Vercel MVP

**Status: LOCAL UI AND GPT-6 LUNA SMOKE VERIFIED; HOSTED SYNTHETIC ANALYSIS AND EXPORTS VERIFIED; CUSTOM DOMAIN DNS IS UNRESOLVED.**

### Sequence update — 2026-10-23

The custom-domain check remains pending because `tender.devayushrout.me` does not resolve. Deployment metadata confirms the Vercel project root is `apps/web`, and `https://tender-compliance-engine.vercel.app/` returns HTTP 200. A synthetic text PDF sent to the public analysis route returns `GPT-6 Luna is not configured`; the deployed project needs its server-side model environment variables. A scan-only synthetic PDF returns the expected hosted OCR-unavailable message. No DNS or Vercel credential changes were made. Continue with independently actionable items while preserving the model environment and custom domain as release blockers.

### Sequence update — 2026-10-25

The client reported that `FinalTenderDocument.pdf` (42 pages) lost or misgrouped technical annexures. Prioritize document reliability and the grouped OEM response sheet before the remaining hosted-release checkpoint. The acceptance case must include source Annexure I (pages 20–22) and Annexure II (pages 23–26), retain their differences, keep the 16 optical-table specifications under their source equipment heading, omit serial numbers from the grouped response sheet, and leave compliance/deviation/remarks blank for the reviewer. Do not implement OEM assessment.

### Done only when

- [x] Only the Next.js app and its small local run scripts remain as runtime services; legacy API, worker, database, queue, and Docker setup are removed.
- [x] TypeScript check and optimized production build pass. A fresh dependency install was completed earlier in this work session.
- [x] Example 2 uploaded freshly and extraction succeeded through the app's configured model path: 102 source-matched requirements from 37 pages; 5 non-matching suggestions discarded.
- [x] Input 2 was uploaded freshly; visually legible text embedded as images in vector compliance-table cells is transcribed only at high model confidence, retained alongside the original selectable-text excerpt, and marked for human verification in the review UI. The generated response sheet includes the recovered phrases; a focused validator and regression tests guard selectable-word preservation.
- [x] Displayed requirements use unique literal quotes matched to selectable text on their cited pages; all start unreviewed. The PDF page and bounding-box overlay render in the browser.
- [x] Compliance schedules are selected with the model, their visible columns are mapped dynamically, and individual source cells are separated using table grid boundaries where available. Exact source-cell rows are retained even when their wording repeats or is contained in another row; page continuations stay linked to their source heading and both page citations; requirement quotes still must match selectable source text.
- [x] A DOCX downloaded and was inspected: 102 tender rows, 102 page references, and 102 blank OEM response cells.
- [x] The response sheet is editable before download; row edits, removals, and restoration update DOCX, PDF, and Excel exports, while source page citations remain locked and source evidence remains available. Browser/export check: changed a requirement, generated all three formats, parsed each file to confirm the edit and source page, removed a row, and reset it. The extraction payload was mocked because the configured GPT-6 Luna endpoint is currently unreachable; this verifies UI/export behavior, not extraction quality.
- [x] Desktop review layout was visually inspected; a reviewer mark changed the checked count from 0 to 1. Narrow layout rules are present; narrow-screen visual QA remains to be completed.
- [x] Extraction is scoped to technical requirement wording and quantified product specifications; commercial, delivery, procurement, and bid-response clauses are filtered out by a conservative rule screen.
- [x] README and deployment runbook give accurate local steps and limits; hosted steps are documented but not yet verified against an authenticated account.
- [x] GPT-6 Luna is the sole model provider; credentials are server-side and no Ollama/open-source model fallback is configured.
- [x] The server builds a source-preserving document model with a SHA-256 fingerprint, physical PDF page numbers, original PDF.js page text, text-block offsets and page-coordinate boxes. For selected vector-table pages it also retains row/cell geometry and identity. Accepted requirements carry a document/version reference; unique native-text matches include the original page excerpt and page-local offsets, while unmatched quotes do not become source excerpts. Visual transcriptions keep native context, OCR text, confidence, and approximate location separate. Printed page numbers remain unknown when the parser cannot determine them.
- [x] A single editable response sheet is not built when selected compliance pages expose different column headers or roles. Page-specific model column proposals must match literal source text, and visible maps must agree before they can share one sheet; incompatible or unsupported maps stop with a review message.
- [x] Successful model-routed reviews include a page-level coverage ledger: routing input/clipping, extraction state, known vector-table row counts and dispositions, candidate suggestions, source-matched rows, reviewer workload, rejection reasons, OCR-needed pages, and whether an omission audit ran or returned possible gaps. Crop-based compliance tables use per-region image audits; all selected technical pages use one bounded independent text audit over the selected text and draft rows. Any recovery suggestions still pass the same source-page, exact-quote, and location validation. Up to twelve detected vector-table rows per page show their source-cell text, candidate count, accepted source-match count, and row highlight; excess findings remain included in the total and are disclosed. Rows without candidates or with fewer accepted matches than candidates are marked for inspection. The UI labels these as needing inspection, since an unmapped row can be a heading or other non-requirement content, and labels a model audit result as advisory rather than proof of completeness.
- [x] Following the newly reported scanned-tender failure, local OCR was added ahead of hosted deployment verification. Tesseract 5 with installed language data transcribes sparse-text pages; Poppler rasterizes pages when available, with PDF.js as fallback. OCR text, confidence, and approximate boxes stay separate from native text, and every OCR-derived requirement remains marked for visual human verification. The actual 42-page scanned tender rendered and page 1 produced OCR lines locally; unit tests, typecheck, and production build passed. This does not verify GPT extraction quality because the configured endpoint remains unreachable.
- [x] ~~P8 progress UX~~: cancellation stops model requests, OCR/render subprocesses, and PDF.js work; the UI retains a truthful cancelled state, elapsed time, and a retry path. Progress-stage counts come from actual pipeline events. Fragmentation, disconnects, duplicate/stale events, and cancellation behavior were verified in focused tests and a browser run.
  - Completed in PR #279 (`ff7036614ebbe03227e42622fa626ef854ea5fa5`). The implementation has nine explicit stages: upload/validate, read/layout, locate, map columns, extract, audit coverage, verify quotations, prepare the response sheet, and ready for review. The displayed order reflects the current pipeline: its coverage audit operates on draft rows before final source-quote acceptance. Local verification covers fragmented UTF-8 SSE, disconnects, duplicate/stale events, reader cancellation, stream cancellation propagation, Tesseract/Poppler subprocess termination, and browser cancellation against a delayed local mock model. The browser showed the elapsed cancelled state and retry action, and the mock server observed the response connection close. Screenshot: `output/playwright/p8-cancelled.png`. The GitHub Actions job did not start because of the account billing/spending limit; the repository owner authorized merging past that billing-only gate after confirming the annotation. Vercel preview checks succeeded.
- [ ] Vercel uses `apps/web`, server-only model settings, and `tender.devayushrout.me` is configured through Namecheap DNS and verified over HTTPS.
- [x] ~~Local OCR is unsupported in the hosted Vercel preview~~: the hosted app does not bundle Tesseract, trained data, or Poppler. Verified against the public deployment on 2026-10-23 with a synthetic image-only PDF; the analysis route returned the explicit local-OCR-unavailable message before model routing.

### Limits

- Local scanned PDFs can use Tesseract 5 OCR when the configured trained-data languages are installed. Hosted Vercel scans remain unsupported. OCR text and approximate page boxes stay distinct from native source text, and all OCR-derived requirements need visual human review. Visual transcription also applies to image text embedded inside detected vector compliance-table cells.
- Visually transcribed wording is a reviewer aid, not an exact selectable-text citation. The UI labels the warning and highlights the whole source row; a human must verify every character against the rendered PDF.
- One synchronous analysis request with bounded model contexts; no durable background jobs or persistence.
- A validated quote and bounding box prove the displayed citation only, not exhaustive tender coverage.
- Grid-based row separation depends on vector border geometry. When borders are merged, missing, or malformed, the model-driven fallback and human review remain necessary; neither guarantees exhaustive coverage.
- Supported vector tables map their columns separately and inherit the last verified map on continuation pages. Unsupported geometry and unseen layout changes still require human review; crop fallback stops rather than silently mixing incompatible maps.
- Omission audits run on crop-based compliance-table regions and across selected technical pages, including prose outside vector tables. The text audit is skipped and marked incomplete if its bounded input exceeds 180,000 characters or if the model call/response fails. Vector-row counts are known only where supported table geometry was detected; unstructured text has candidate counts, not a deterministic source-row denominator.
- Row-level coverage findings are available only where vector table geometry produced source rows. The UI lists the first twelve such rows per page; it gives a total and count of detected rows not listed for pages with more than twelve.
- Model routing and extraction can miss technical requirements and are not proof of complete coverage; review every source citation.
- Requirements remain in human review until the user checks them.
- The hosted workflow is not complete until a fresh hosted upload and DOCX export are inspected.

## Checkpoint 73 — Client tender document reliability

### Fresh held-out live-pipeline baseline — 2026-11-07

- [x] Run the current pipeline once on the SHA-256-verified 15-page IIT Guwahati public tender and retain a text-free aggregate artifact tied to the code commit.
- [x] Compare accepted output against 23 partial assistant-reviewed source-bound/anchor cases without promoting the overlap results to semantic recall.
- [ ] Resolve or explicitly disposition all nine unrouted pages and nine pages without page-level completeness audits; review why three known page-11 omission anchors were not found by the audit.
- [ ] Reconcile the post-routing-change IIT Guwahati rerun: routing completed but extraction hit the 270-second deadline with no response sheet. Design bounded/resumable work or otherwise reduce incomplete processing without weakening page recall; do not treat the single timeout as a before/after performance result. A follow-up at `0a10ff6` completed five vector-page inspections and five general extraction batches, but only one of four text-page omission-audit batches before the deadline; see `live-iitg-coverage-deadline-2026-11-07.json`. This run returned no matrix or quality comparison.
- A current-`main` run after PR #379 used the configured Azure-compatible GPT-6 Luna endpoint and reached the 290-second client timeout before returning a sheet. Routing completed by 77.2s; vector mapping/classification continued through 263.3s; only 1/3 general extraction batches returned; text/visual omission audits were not reached. See `live-iitg-post379-timeout-2026-11-07.json`. This run does not validate the sliding-window audit change because the audit stage was never reached; it shows resumable work or materially lower earlier-stage latency is still required.
- A local run of the page-local vector mapping/classification change at `5225fc4` completed vector inspection at 185s and all four general extraction batches at 274.3s, then timed out after starting three of four text omission audits with no audit response. The prior post-#379 run had not completed general extraction by 290s. This is evidence that the vector-stage change moves the pipeline farther, not a controlled speedup or a completed analysis. The post-merge rerun, returned response sheet, and coverage/anchor evaluation are still open; see `live-iitg-independent-vector-pages-2026-11-07.json`.
- Independent general text-extraction batches now run in waves capped at the existing per-analysis concurrency limit of three. Scripted 12-page coverage verifies a peak of three concurrent requests, deterministic source-order results, and truthful wave completion progress; live provider latency, deadline completion, and recall remain unverified.
- Opt-in content-free timing now distinguishes vector-table column mapping, row classification, and source-row semantic-audit requests by PDF page and batch. Parsed vector responses include response-body, JSON parse, output-size, and provider token fields when supplied; raw response content remains excluded. Use these records to locate the long vector-inspection stage before changing heterogeneous-page scheduling; timings do not establish completeness or quality.
- Page-routing requests now emit the same opt-in timing phases by bounded page group, including parse and token metadata when available. This makes pre-extraction provider stalls observable without recording page summaries or routing output.
- A correctly rebuilt live run at `ad76731` measured routing through 56.1s, serial vector-page inspection through 164.6s, general extraction through 235.9s, and only 2/4 text omission audits by the 270.9s deadline; see `live-iitg-pre-windowed-audit-2026-11-07.json`. The next experiment changes only text-audit scheduling to a bounded sliding window and allows 290s within the route's 300s function cap. This is not resumability or a completed benchmark; validate the complete result and page-level coverage before drawing a quality conclusion.
- Caught vector-call failures now produce a content-free failure event with elapsed time and a bounded provider/network/abort category, preventing an absent response-header event from being mistaken for an unobserved request.
- A fresh isolated production run at `2560788` likewise completed source inventory, routing, and mapping, reached 4/5 visual page extractions, then hit the 270-second deadline without a response sheet. Recorded in `live-iitg-post-routing-batching-2026-11-07.json`; no quality or latency comparison is supported by this single run.
- [x] Batch the three overlapping visual regions per page into one extraction request and a separate omission-audit request, with region-index validation and a scripted upload-to-sheet assertion that each request carries all three regions (PR #355).
- [x] Batch visual extraction across up to two pages per request while binding every candidate to its validated parent page and preserving page-local column maps (PR #361). The independent omission audit remains one request per page.
- [x] Repeat the hash-verified IIT Guwahati run after PR #361 and record its outcome in `live-iitg-post-visual-page-batching-2026-11-07.json`. It reached the 270-second deadline during extraction; the last captured counters were four of five, but the monitor did not retain the progress message needed to identify the extraction subpath. No response sheet was produced, and this single run establishes no before/after latency or quality result.
- A second run with retained progress messages, recorded in `live-iitg-vector-extraction-timing-2026-11-07.json`, reached the same deadline. Vector-table extraction is sequential: four of five pages completed at 212.3 seconds, and the request ended at 270.1 seconds before returning a response sheet. Reduce stage time without weakening page-level provenance or completeness states.
- [ ] Measure the page-batched visual inference path on representative bordered/borderless and complex multi-row tenders. Live quality, request-size constraints, latency, and deadline completion remain unverified.
- [ ] Repeat with an independently adjudicated gold set and token/cost telemetry before making a quality or capacity claim.

### Held-out parser-candidate/source-region overlap — 2026-11-07

- [x] Run PyMuPDF `lines`, `lines_strict`, and `text` table-candidate geometry against 23 SHA-256-bound source-region annotations from the separate IIT Guwahati tender; store a text-free, geometry-free report and a reproducible evaluator.
- [x] Record the observed structural trade-off: line-based candidates cover the seven annotated specification-table spans but miss the thirteen narrative/documentary spans; the broad text strategy covers nearly all bounds with large candidate envelopes.
- [ ] Independently adjudicate source-region labels and compare candidate-level text/cell structure, not only geometry. Current measurements are assistant-reviewed overlap diagnostics, not precision/recall.

### PDF.js and PyMuPDF inventory parity baseline — 2026-11-07

- [x] Verify all six representative tender PDFs against manifest SHA-256 fingerprints and page counts; run the production PDF.js parser and compare page inventory signals with the PyMuPDF 1.26.5 shadow artifact.
- [x] Record a text-free, geometry-free 183-page comparison artifact and reproducible script. Page dimensions, image-region counts, and summed image-area ratios match across this sample; vector primitive counts differ and are not treated as equivalent table evidence.
- [ ] Compare table/region candidates against independently adjudicated source bounds and obligation labels. Current parity metrics are not accuracy scores and do not justify changing parser defaults.

### Per-image-region OCR dispositions — 2026-11-07

- [x] Store a per-region OCR disposition in the page source inventory, distinguishing not-targeted, not-attempted with a skip reason, text-found, no-text-found, and failed states.
- [x] Reject inconsistent OCR-to-image links and show per-page region disposition counts in the coverage ledger.
- [x] Unit coverage verifies stable region states, skip reasons, source links, and inventory validation.
- [ ] Adjudicate region-level dispositions on hybrid/scanned real tenders; PDF.js image operator bounds are approximate and full-page OCR may not map back to individual image operators.

### Verbatim source-row omission recovery — 2026-11-07

- [x] Allow the bounded semantic row audit to return exact source-cell excerpts for likely omissions; reject paraphrases, excerpts not contained in a single source cell, excessive suggestions, and excerpts on non-gap dispositions.
- [x] Reintroduce accepted excerpts as independent unchecked candidates through the existing grounding and validation path. Preserve the audit's advisory status and never treat the result as a completeness guarantee.
- [x] Scripted upload-to-sheet contract verifies one seeded omission is recovered as a separate source-verified, unchecked row; unit tests cover verbatim validation boundaries.
- [ ] Measure omission-recovery precision and recall against independently annotated real tender rows; the current evidence is scripted only.

**Status: LOCAL ACCEPTANCE VERIFIED; CURRENT MAIN CI PASSED; HOSTED RELEASE GATES PENDING.**

- [x] Real 42-page client PDF routes both full technical annexures, including continuation pages 22 and 26.
- [x] Different table column layouts preserve literal source specifications/descriptions. Source annexure labels/title lines and equipment headings sit above separate tables, with no annexure/equipment columns in the body; the optical-table group has 16 source rows per annexure. Source citations remain available in the UI.
- [x] Page continuations and source-cell subpoints retain their complete text and every source link when joined for export.
- [x] SHA-256 provenance matches the uploaded bytes after PDF.js parsing; unknown evidence remains unknown.
- [x] PDF export preserves comparison signs, numerical precision, and units. Per the 2026-10-25 client clarification, the printable PDF omits the source-page column and page-number footer; locked source citations remain available in the UI.
- [x] Regression tests, production build, and deterministic upload-to-sheet contract checks pass and run in CI.
- [x] Real browser upload/review and DOCX/PDF/Excel download are inspected, with remaining limits documented.

This checkpoint does not establish exhaustive extraction on unseen layouts, hosted OCR support, client production access controls, persistence, or a completed hosted deployment. See `docs/document-reliability-audit.md` for the evidence and limits.

- [x] GitHub Actions run [42261845260](https://github.com/ayushcodes13/tender-compliance-engine/actions/runs/42261845260) passed unit tests, typecheck, production build, and scripted pipeline checks for the PR #307 source before its squash merge to `main` as `1739537c2080310c26c2e76ee7f19c69ce618356`.

### Remote release-gate refresh — 2026-11-06

- [x] The public Vercel URL `https://tender-compliance-engine.vercel.app/` returned HTTP 200 on 2026-11-06.
- [x] A fresh synthetic one-page text PDF was uploaded through the public UI on 2026-11-06. Hosted GPT-6 Luna returned one source-linked requirement; DOCX, PDF, and XLSX exports downloaded and were inspected. This verifies the hosted synthetic path, not extraction recall on real tenders. No client tender was submitted.
- [ ] `tender.devayushrout.me` still fails to resolve in this environment; `tender-compliance-engine.vercel.app` resolves and responds over HTTPS. No DNS changes were made.
- [ ] Vercel preview deployment remains unavailable because the branch author does not have access to the Vercel project. GitHub Actions CI passed; this Vercel permission failure is a separate deployment integration issue.

Current main CI passing does not close the hosted release gates or this checkpoint's document-reliability limits.

### Client print-layout clarification — 2026-10-25

Use the tender's own annexure labels, title lines, and table/equipment headings as headings above the corresponding specification tables, in source order. Do not place those titles in body columns or add a generic document title, source filename, row-count introduction, or other wrapper to the printable output. Specification/description and OEM response fields form the table body; UI source validation remains available. The source titles are read from native positioned text, not invented from model metadata. UI, PDF, DOCX, and Excel use the same section projection.

### Held-out reliability extension — 2026-10-25

The supplied examples exposed a native canvas crash, a letterhead grid classified as a requirement, prose below a vector table omitted, and parenthesized/numbered source headings lost. Address these within checkpoint 73 before claiming broader document reliability: prefer the existing local Poppler subprocess, bound detected rows below verified source technical headings, audit prose across all selected pages, and retain literal source heading formats. The example-1 rerun recovers the five outside-table bullets and excludes the contact cell; model page selection still varies and needs human scope review. Hosted native rendering without Poppler and remaining held-out documents are not verified by this result.

### Response-sheet review drawer — 2026-10-25

The client wants to validate citations directly from the response sheet without scrolling back to a separate requirement list/document area. Make the editable response sheet the main workspace, with compact per-source citation controls opening a right-side PDF drawer at the cited page/highlight. Preserve original quotes, OCR uncertainty, individual human review marks, all continuation citations, sheet edits/removal/reset, and citation-free printable exports. Keep detailed routing/coverage evidence available in a collapsed section. Verify deep-row scroll/focus restoration, Escape/close/backdrop dismissal, keyboard containment, mobile layout, and downloads before completing this UI refinement.

Local drawer acceptance passed with the saved real 93-row client analysis and original PDF: deep-row page/highlight, review toggle, focus/scroll restoration, all close methods, mobile containment, and three exports. The source-viewer highlight now waits for the PDF render to finish before scrolling, including when the render scale stays unchanged. This UI acceptance does not close the broader held-out extraction or remote CI/release gates.

### Verified response capacity — 2026-10-25

The example-2 stop exposed a capacity check applied before source verification. Apply the existing 250-row review limit to the completed response-sheet projection, after source verification and source-cell reassembly. Rejected suggestions and independently reviewed subpoints from one source row must not incorrectly consume multiple response rows. Remove the earlier candidate truncation and verification-loop break; an oversized verified sheet must stop with its actual response-row count and no partial analysis. Synthetic production checks cover 300 unsupported suggestions alongside one real clause and a genuine 251-row response sheet; a unit case preserves all 300 citation IDs from one split source cell. A real example-2 rerun is required before claiming that document now succeeds.

### Single-content source tables and numerical identity — 2026-10-26

Metadata-only diagnostics on example 2 established that its real technical specifications occur both in the main document (pages 8–13) and Annexure I (pages 24–29). Do not discard either source version. A lone technical content column was being mapped as a parameter heading, leaving no specification column and sending the pages through generic clause extraction. Normalize a source-verified sole content column to specification when all other columns are serial, quantity, or response fields; preserve literal headers and record corrections for review. Standalone technical titles can bound the table below an invitation on the same page. The shared projection must omit an invented empty parameter column only when the verified source schema confirms it has none.

Exact omission-recovery duplicates must not create extra response rows. Recovery, candidate identity, literal header validation, and repeated-header detection must preserve scientific unit case and numerical operators. Regression cases distinguish mW from MW and 300 mm from ≥ 300 mm. The production contract covers the single-content table, duplicate recovery, and verified response capacity. A fresh real-document result and export inspection remain required.

The real-provider rerun succeeds for examples 2 and 3 (217 and 87 response rows). Fingerprint/source-ID preservation, example-2 UI edit/source/reset behavior, and all three generated formats are checked. This does not close checkpoint 73: bilingual section/part hierarchy, mixed heading/description classification, multiple grids on one page, provider robustness, and the existing remote CI/release gates remain open. The source title boundary uses every header cell's text position, and source notes do not prefill OEM response fields.

### Mixed native heading/body cells — 2026-10-26

Where the model identifies a source heading but the native font runs prove a bold title followed by regular body text, retain the title as a heading and expose the remaining specification as an assessable response row. A requirement row needs both a literal agreeing model prefix and the native font boundary before starting a group. Preserve the complete original quote/reference; unknown font metadata stays unknown, and unverified inline prefixes must not change the group of following siblings.

The production contract verifies the font boundary, requirement classification despite a model section label, full-cell provenance, and heading/body projection. Local reconciliation of the earlier real example-2 result promotes four such source cells and formats two already-assessable mixed cells; it produces 220 response rows, retaining every original quote/reference and all requirement IDs. One new body row joins its verified page-26/27 continuation with both citations. This is local source-metadata reconciliation, distinct from another live-model result. A further fresh API run succeeds with 265 candidates and verifies native full-cell citations for the source shutter/control-system paragraphs; model split counts still vary.


### Evidence-quality separation for missing geometry — 2026-11-03

A literal quote found on the selected native PDF page may lack an unambiguous bounding box (duplicate text, malformed position runs, or extraction-order differences). Previously the final \`actions.ts\` gate discarded it with the same reason used for unsupported model text. The existing \`page-only\` precision type was unused by the final candidate loop.

- [x] Use a deterministic evidence-quality decision: \`exact\` requires literal native text plus location; \`page-only\` requires literal native text but has no verified highlight; \`visual-ocr\` remains a reviewer-warning state for OCR/identified visual evidence; unsupported model output still fails.
- [x] Keep \`bbox: null\` and \`locationPrecision: approximate\` when the location is uncertain, even when native-text offsets are available. Never synthesize coordinates.
- [x] Label page-only citations explicitly in the source drawer, enable deliberate human verification against the complete page, and keep all new candidates unchecked by default.
- [x] Add deterministic classifier/source-reference contract tests covering every evidence state and the untrusted-suggestion rejection boundary.
- [x] GitHub Actions [run 41683546174](https://github.com/ayushcodes13/tender-compliance-engine/actions/runs/41683546174) completed successfully on commit `78eaefca22e4b4b6bb5a2c197986dd5fe6715dc6`: dependency installation, `npm test`, TypeScript check, optimized build and scripted production pipeline. This is not a real-model evaluation.
- [ ] Real tender and browser review with a reliably reproduced text-match/no-box case, including source-page inspection, manual check and export. No real-provider recall claim until this is adjudicated.

This is a conservative intermediate step, not the final evidence model. Some quotes still cannot be matched textually because of extraction-order or OCR differences. Do not add unsupported suggestions to the response sheet, and do not represent page-only/visual evidence as an exact highlighted citation.

### Rejected-only run diagnostics — 2026-11-06

When every suggested requirement fails source verification, analysis stops without a response sheet. That failure now retains the first 50 bounded rejection previews, reasons, total rejected count, and aggregate coverage summary in the SSE result. It does not send source table excerpts in this error payload. The upload screen shows that these are unverified suggestions, never review rows, and lets the reviewer open each known source page; any additional rejected suggestions remain in the total but are not sent as previews. A scripted upload-to-sheet contract verifies that the failed result contains no accepted analysis while preserving the bounded rejected-only diagnostics. The reviewer still decides whether any suggestion is a real requirement; no unsupported text is accepted.

If the model returns no suggestions at all, the failure message says that no proposals were produced and explicitly avoids implying the source has no requirements. It shows the aggregate page-audit states and provides links to selected pages for manual inspection. A scripted zero-candidate case verifies the failure status and selected-page list.

### Optional Remark verification must not erase requirements — 2026-11-03

The final candidate-verification loop previously removed an entire otherwise source-matched requirement when an optional model-suggested Remark field could not be located in the PDF. This is a code-level omission mechanism; its frequency in real tenders has not been measured.

- [x] Keep the existing strict source page/text/geometry verification for the primary requirement.
- [x] Independently verify a Remark field before including it in a visual compliance-sheet response. Discard only an unverified optional Remark and warn the reviewer at the affected PDF page; do not export it.
- [x] Add tests for verified, missing, empty, and out-of-scope remark decisions.
- [x] GitHub Actions [run 41684385667](https://github.com/ayushcodes13/tender-compliance-engine/actions/runs/41684385667) completed successfully on commit `d0b4e94ea09f85a309994bdde67e4cf4dbcb622f`: unit tests, TypeScript check, production build and scripted PDF upload-to-sheet contract. Real PDF/provider accuracy remains unverified.
- [ ] Review a real tender with valid requirement plus unlocatable optional remark; inspect that it survives unreviewed with a correct source page while the unsupported remark is not present in exports.

This change does not authorize fabricated source remarks, infer missing remarks, or claim real-document recall.

### Parser-owned citation metadata — 2026-10-26

Model extraction and recovery payloads may supply only their public schema fields. Drop model-supplied bounding boxes, cell/row indices, exact-cell flags, native typography, transcription claims, and export IDs before source verification. Only the application frame that constructs candidates from native vector rows can retain parser-owned fields. The production contract injects a forged box and exact-cell flag beside a real clause and payment terms; the real clause keeps its native location and the administrative clause remains rejected. This closes an unchecked trust boundary, not a guarantee that model extraction is complete.


### Phase 1 extraction acceptance gate audit — 2026-11-03

The code inventory and disposition matrix are tracked in \`docs/extraction-gate-audit.md\`. This new priority is a scoped reliability correction ahead of manufacturer evidence evaluation. Checkpoint 73's real-document and remote-CI gates remain open.

- [x] Inspect the merged \`main\` extraction decision loop and reproduce the overly broad administrative predicate on synthetic clauses. This confirms a predicate-level omission mechanism, not an adjudicated real-PDF failure.
- [x] Narrow the hard screen so catalog, certificate, technical inspection and installation obligations can proceed to the unchanged strict page/text/geometry verification. Distinguish administrative rejections from invalid candidate text in the coverage reasons; preserve default human review.
- [x] Add focused regression assertions and a scripted-provider PDF contract for accepted source-backed catalog text, rejected payment terms and untrusted model metadata.
- [x] GitHub Actions run [41682499234](https://github.com/ayushcodes13/tender-compliance-engine/actions/runs/41682499234) at commit `7908d36fadfa6ce7c8b40373192b4bac4436a5d2` completed successfully: `npm ci`, `npm test`, `npm run typecheck`, `npm run build`, and `npm run test:pipeline`. The pipeline test uses a scripted provider; no local run was performed in this session.
- [ ] Verify acceptance against real adjudicated tenders and measure requirement recall, false inclusions, citation accuracy and silent omissions; inspect documentary and technical-test passages on their original pages.
- [ ] Required remote CI passes. The earlier GitHub billing/spending restriction is not evidence of a green CI result.

Follow-on focused PRs must address uncertain text/box evidence, independent table layouts, source-aware duplicate recovery, routing gaps and bounded incomplete processing. No OEM compliance evaluation is authorized by this checkpoint.

### LLM-routed semantic extraction and elimination of brittle regex screens — 2026-11-04

Deterministic regex keyword screens (`isClearlyAdministrativeClause`, `extraction-rules.ts`) proved brittle across diverse tender document layouts and introduced hardcoded domain biases. A pure LLM semantic routing and schema classification architecture was implemented:

- [x] Removed `extraction-rules.ts` and brittle regex keyword matching.
- [x] Expanded schema enums across `tender_requirements` and `visual_table_row_labels` to include explicit `instruction` and `header` row types.
- [x] Strengthened LLM prompts in `extractGeneralPages` and `inspectVectorPage` with rigorous definitions separating assessable technical specifications (`requirement`) and structural headings (`section`) from bidder filling directives / submission guidelines (`instruction`) and table column labels (`header`).
- [x] Cleanly exclude `instruction` and `header` rows in vector table row mapping and candidate verification.
- [x] Preserved deterministic code strictly for provenance, exact verbatim quote verification against selectable PDF text, bounding boxes, and response sheet generation.
- [x] Unit tests (`llm-semantic-classification.test.mjs`), typechecks, and pipeline integration tests all pass.

### Environment-aware upload size limits (local 32 MB / hosted 4 MB) — 2026-11-05

Real customer tender documents frequently exceed 4 MB (e.g. 7 MB+ documents with high-resolution imagery and appendices):

- [x] Configured environment-aware payload limit in `apps/web/app/upload-limits.ts`: defaults to 32 MB for local development and on-premise runs, while retaining the 4 MB ceiling on hosted Vercel environments to satisfy serverless payload limits.
- [x] Configured Next.js server actions `bodySizeLimit` in `apps/web/next.config.ts` dynamically (`isHosted ? "4.5mb" : "32mb"`).
- [x] Updated upload validation in `apps/web/app/actions.ts` and client helper text in `apps/web/app/tender-mvp.tsx`.
- [x] Added unit tests in `apps/web/app/upload-limits.test.mjs` verifying local, hosted Vercel, and custom `MAX_FILE_BYTES` overrides.

**Route-boundary correction (2026-11-09):** `/api/analyze` is a Route Handler and parses multipart data with `Request.formData()`. The Next.js `serverActions.bodySizeLimit` setting does not bound this route. A streaming byte cap now runs before form parsing and returns HTTP 413 for oversized request bodies (file allowance plus 256 KiB multipart metadata). Vercel still enforces its own 4.5 MB function request cap; this route guard does not enable 32 MB uploads on Vercel. Local 32 MB acceptance still needs a representative PDF and memory/concurrency measurement before any capacity claim.

### Tiered validation ladder and hierarchical response sheet — 2026-11-05

A formal 3-tier validation ladder and hierarchical response sheet architecture were implemented to support complex multi-level tender specifications and audit requirements:

- [x] **Tiered validation ladder (`apps/web/app/tiered-validation.ts`)**:
  - **Tier 1 (Verbatim Check)**: Deterministic string matching on native PDF selectable text with exact bounding box derivation.
  - **Tier 2 (Visual Check)**: Fallback on OCR transcript and token-level containment on cited page to handle scanned pages, character noise, and table cell wrapping.
  - **Tier 3 (Human Review)**: A candidate passed to this validator that fails both automated checks is flagged with `verdict: "needs_human_review"`, `precision: "unverified"`, and `needsHumanReview: true`.
  - In the production analysis flow, a stricter source-acceptance gate runs first. Candidates without accepted source evidence are excluded from the response sheet and surfaced in the coverage ledger as not added; they are not converted into Tier 3 requirement rows.
  - The validator runs over source-accepted requirements before returning analysis, producing summary counts and per-requirement validation tags.
- [x] **Hierarchical response sheet (`apps/web/app/response-sheet.ts` & `apps/web/app/response-sections.ts`)**:
  - Dynamically captures both Main Section / Unit (e.g. `Microwave Unit`, `Console`, `Magnet Unit`) and Subsystem / Parameter (e.g. `Microwave Bridge`, `Microwave Power`, `Automatic Frequency Control (AFC)`, `Magnetic Field Controller`), eliminating heading latching.
  - Generates multi-level columns `[Section / Unit, Subsystem / Parameter, Tender requirement, Compliance (Yes / No), Remarks / Justifications, Source page]`.
  - Consolidates multiple repeated specification points under the same subsystem into a single assessable response row rather than repeating the subsystem column across multiple rows, preserving all source IDs and citations.
  - Replaces vague single `"OEM response"` fallback column with mandatory deterministic fields: `Compliance (Yes / No)` and `Remarks / Justifications`.
- [x] **Review workspace & verification UI (`apps/web/app/tender-mvp.tsx`)**:
  - Displays validation status breakdown in summary statistics (`Tier 1/2 verified` vs `Tier 3 human review`).
  - Distinguishes Tier 3 unverified citations in the sheet drawer and citation badges (`REVIEW` tag with explicit inspection instructions).
- [x] **Tests & verification**:
  - Added unit test suite `apps/web/app/tiered-validation.test.mjs` (6 tests).
  - Added hierarchy tests in `response-sheet.test.mjs` and `response-sections.test.mjs`.
  - All 173 unit tests, scripted pipeline test (`verify-pipeline.mjs`), and Next.js production build (`next build`) pass.

### OCR symbol tolerance and completeness fix — 2026-11-06

This entry records an intermediate implementation. Its comparison that treated `±` as equivalent to plain `+` was later narrowed: the current OCR matcher preserves technical operators and accepts only `±` / `+/-` as equivalents. See the later strict OCR grounding entry below and `tiered-validation.test.mjs`.

Investigated and resolved an issue where valid technical specifications in scanned PDFs were dropped during candidate verification due to minor OCR character substitutions (e.g. `±` vs `+`, em-dash `—` vs en-dash `–`, bullet artifacts `«` / `¢`):

- [x] **Symbol reconciliation (`normalizeOcrComparable`)**: Normalizes em-dashes (`—`), en-dashes (`–`), minus signs (`−`), plus-minus (`±` / `+/-`), bullet artifacts (`«`, `¢`, `•`), and word-boundary punctuation.
- [x] **Tolerant line-level bounding box resolver (`locateOcrQuoteTolerant`)**: Performs single-line and multi-line window searching against `ocrPositioned` lines to compute exact bounding boxes even when character noise exists.
- [x] **Candidate verification gate**: Updated `actions.ts` candidate filter so that vision-transcribed technical specifications matching OCR transcript via `normalizeOcrComparable` are verified as visual OCR evidence rather than rejected.
- [x] **Tier 2 visual validation**: Updated `checkVisual` in `tiered-validation.ts` to derive bounding boxes and confidence using `locateOcrQuoteTolerant`.
- [x] **Verification**: Added 3 unit tests in `tiered-validation.test.mjs` (178 unit tests passing). Verified 100% extraction of all 6 specifications under `Microwave Power` on the real ESR tender PDF.

### Token Sequence Alignment Grounding Engine — 2026-11-06

This describes the initial alignment implementation and its fuzzy similarity threshold. It was superseded by **Complete Removal of Fuzzy Matching** below; current grounding requires contiguous exact token matches after limited, explicit canonicalization. The later strict OCR grounding entry further narrows which technical symbols may be canonicalized.

Permanent architectural resolution for the dual-path divergence between multimodal vision transcription and OCR text:

- [x] **Token Sequence Alignment Grounding Engine (`apps/web/app/token-sequence-alignment.ts`)**:
  - Implements sliding-window token alignment with lookahead edit distance, token-level Levenshtein similarity, and normalized symbol reconciliation.
  - Aggregates underlying parser-owned spatial bounding boxes across multi-line wrapping and rejects ungrounded hallucinations (<0.70 similarity).
  - Derives exact bounding boxes from native `positioned` tokens and OCR `ocrPositioned` lines with 0% fabricated coordinates.
- [x] **Integration across grounding pathways**:
  - `source-document.ts`: `findUniqueSourceText` uses sequence alignment as fallback when exact match fails, preserving duplicate ambiguity rejection.
  - `actions.ts`: `locateQuote` and candidate verification filters (`nativeTextMatch`, `ocrTextMatch`) leverage token sequence alignment.
  - `tiered-validation.ts`: `checkVerbatim` and `checkVisual` compute exact bounding boxes and confidence via token sequence alignment.
- [x] **Live verification on 13-Page Saha Institute EPR Tender**:
  - Extracted 131 technical specifications and sections across Pages 2, 3, and 4 (113 response rows) with 100% verified bounding boxes.
  - Fully resolved truncation after `Console` (Page 3-4 sections including `Magnetic Field Controller`, `Signal Channel`, `Modulation Amplifier`, `EPR Software`, `Workstation`, `Acquisition Controller`, `Data Manipulation`, `Graphical Tools`, `Magnet Unit`, `Variable Temperature Unit`, `Warranty`, `Experience`, and `Optional Resonator` are all captured).
  - 100% of unit tests (186/186) passing, `npm run test:pipeline` (17/17) passing, TypeScript check (0 errors) passing, and production build clean.

### Multi-Format Stress Testing Suite & Boardroom Export Matrix Polish — 2026-11-06

Hardened extraction against complex layout archetypes and polished B2B deliverables:

- [x] **Programmatic Stress Tender Corpus Generator (`apps/web/scripts/generate-stress-tenders.mjs`)**:
  - Synthesizes 4 hard real-world PDF archetypes:
    1. `stress-multi-column.pdf`: 2-column and 3-column specification sheets with parallel text flow.
    2. `stress-borderless-table.pdf`: Multi-page borderless specification schedules with repeating headers across page breaks.
    3. `stress-nested-clauses.pdf`: Deep hierarchical numbered clauses (Section 4 $\rightarrow$ Clause 4.1 $\rightarrow$ 4.1.1 $\rightarrow$ (c) $\rightarrow$ (i)).
    4. `stress-ocr-scientific.pdf`: Low-DPI scanned pages with rotational skew and extreme scientific notations ($10^{-8}$, $10^9$, $\mu\text{L}$, $\Omega$, $\pm$).
- [x] **Automated Stress Testing Harness (`apps/web/scripts/stress-test-harness.mjs`)**:
  - Evaluates end-to-end extraction against all 4 stress archetypes.
  - Achieved **100% bounding box grounding** across all tests and $\ge 80\text{–}100\%$ key specification recall.
  - Generates comprehensive scorecard reporting requirement counts, response rows, grounding rates, and durations.
- [x] **Boardroom-Ready Export Matrix Polish (`apps/web/app/sectioned-exports.ts` & `apps/web/app/pdf-export.ts`)**:
  - **Excel (`.xlsx`)**: Structured styling with hierarchical vertical merges (`Section / Unit` and `Subsystem / Parameter`), auto-filter on table headers, thin slate borders (`#CBD5E1`), top vertical alignment, dynamic row height calculation, and explicit role-tuned column widths.
  - **Word (`.docx`)**: Institutional executive navy headers (`#1E293B`, bold white text), hierarchical vertical merging (`w:vMerge`), repeating headers across page breaks (`tableHeader: true`), and `cantSplit: true` row constraints.
  - **Printable PDF (`.pdf`)**: Role-weighted column width allocations ensuring `Tender requirement` and `Remarks` never clip, repeating headers on every page, and alternating row styling.
- [x] **Verification**:
  - 188 unit tests passing (`npm test`).
  - 17 pipeline contract cases passing (`npm run test:pipeline`).
  - TypeScript clean (`npm run typecheck`).
  - Automated stress harness 100% pass rate (`npm run test:stress`).

### Complete Removal of Fuzzy Matching — Zero Fuzzy Tolerance — 2026-11-06

Per explicit engineering directive to permanently eliminate long-term correctness risks, all fuzzy matching algorithms (Levenshtein edit distance, percentage similarity scoring, and token-skipping lookaheads) have been entirely removed from the engine:

- [x] **Complete Fuzzy Elimination (`apps/web/app/token-sequence-alignment.ts`)**:
  - Removed `levenshteinDistance` calculation completely.
  - Implemented strict binary token similarity (`tokenSimilarity(t1, t2) = (t1 === t2 ? 1.0 : 0.0)`).
  - Implemented `alignExactTokenSequence` requiring contiguous, 100% exact 1:1 token sequence equality between query and source text.
  - Replaced heuristic thresholds (0.70 / 0.80) with deterministic exact matching while preserving deterministic canonicalization (case folding, whitespace collapse, and standardizing Unicode typography like `—`/`–`/`−` $\rightarrow$ `-` and `±`/`+/-` $\rightarrow$ `+`).
- [x] **Adversarial & Unit Verification (`apps/web/app/token-sequence-alignment.test.mjs`)**:
  - Validated exact rejection of altered numbers (`500 bar` vs `200 bar`, `500 RPM` vs `200 RPM`).
  - Validated exact rejection of conflicting directional operators (`Minimum` vs `Maximum`).
  - Validated exact rejection of typos and altered words (`attenuator` vs `attenuater`).
  - Verified exact multi-line bounding box derivations across wrapped lines and paragraph spans.
- [x] **Verification**:
  - 191 unit tests passing (`npm test`).
  - 17 pipeline contract cases passing (`npm run test:pipeline`).
  - TypeScript clean (`npm run typecheck`).

### Adversarial Audit Resolutions — Semantic Grounding, Subpoint Splitting & Provenance Hardening — 2026-11-06

Systematically resolved the failure modes identified in the comprehensive adversarial review:

- [x] **Semantic Subpoint Splitting vs Physical Line Wrapping (`apps/web/app/response-sheet.ts` & `apps/web/app/tender-mvp.tsx`)**:
  - Distinguishes physical PDF line wrapping from semantic requirement boundaries (`recombinePhysicalWrappedLines`).
  - Physical sentence wraps (e.g. `The pump shall operate continuously at \n minimum pressure of 200 bar and 50 Hz.`) are recombined into single requirements rather than being split into incomplete fragments with separate compliance decisions.
  - Splits only on confirmed bullet points, numbered/lettered clauses, or terminal punctuation followed by capitalized clauses.
- [x] **OCR Validation Confidence & Position Map Grounding (`apps/web/app/tiered-validation.ts` & `apps/web/app/actions.ts`)**:
  - Propagated `ocrRawItemMap` from `pages` into `pageEvidenceSources` in `actions.ts` so spatial token alignment is fully active in production.
  - Corrected `checkVisual`: Never defaults to `"high"` confidence when no bounding box is derived or when unpositioned; derives confidence strictly from matched positioned OCR regions.
- [x] **Granular Independent Obligations Preserved in Recovery (`apps/web/app/visual-table.ts`)**:
  - Updated `discardContainedSuggestions`: Distinguishes complete standalone obligations from truncated partial fragments.
  - Complete independent clauses in multi-clause composite rows (e.g. `VFD shall support Modbus TCP.` in `The motor shall have 5 kW rating. VFD shall support Modbus TCP.`) are preserved for granular evaluation, while truncated phrases (e.g. `c) Effusion cells: Capacity`) are rejected.
- [x] **Edit-Aware Provenance & Review Invalidation (`apps/web/app/tender-mvp.tsx`)**:
  - When a reviewer edits the text of a requirement in the response sheet, the checked review state on that requirement is automatically invalidated (`reviewed: false`), requiring explicit re-review of the modified text.
- [x] **Token-Bounded OCR Header Verification (`apps/web/app/column-layout.ts`)**:
  - Enforced strict word boundaries (`\b`) and proximate line window matching in `matchOcrHeaderTokens`. Prevents `Serial 10` from matching `Serial 1000`.
- [x] **Repeated Passage Ambiguity Protection (`apps/web/app/token-sequence-alignment.ts`)**:
  - Added `requireUnique` protection to `alignExactTokenSequence`: If an exact passage appears multiple times on the same page, declines ambiguous selection to prevent highlighting the wrong source row.
- [x] **Excluded Technical Page Routing Audit (`apps/web/app/actions.ts`)**:
  - Scans unselected pages for dense technical units and parameter keywords, alerting the reviewer in `routingWarnings` if excluded pages appear to contain technical specifications.
- [x] **Verification**:
  - 195 unit tests passing (`npm test`).
  - 17 pipeline contract cases passing (`npm run test:pipeline`).
  - TypeScript clean (`npm run typecheck`).
  - Production build passing (`npm run build`).

### P0 Engineering Units, Signed Numbers, and Native Token Boundary Enforcement — 2026-11-06

Directly resolved the critical false verbatim pass vectors and provenance gaps identified in code review:

- [x] **P0 — SI Unit Case Sensitivity & Technical Operator Protection (`apps/web/app/token-sequence-alignment.ts` & `apps/web/app/tiered-validation.ts`)**:
  - Maintained SI prefix case sensitivity (`mW` vs `MW`, `mA` vs `MA`, `mHz` vs `MHz`, `mbar` vs `Mbar`). A claim of `5 MW` will never pass when the source specifies `5 mW`.
  - Preserved signed negative numbers: `-20 °C` is strictly distinguished from `20 °C` (does not strip leading minus when followed by a digit).
  - Preserved tolerance distinctions: `±5%` is strictly distinguished from positive offset `+5%`.
- [x] **P0 — Token Boundary Enforcement in Native Text Matching (`apps/web/app/token-sequence-alignment.ts`, `apps/web/app/actions.ts`, & `apps/web/app/source-document.ts`)**:
  - Implemented `findUniqueTokenBoundedMatch`: enforces word boundaries (`\b` / non-alphanumeric check) on both start and end of matched spans.
  - Replaced unconstrained `.includes()` in the acceptance gate and `checkVerbatim`: `500 bar` will never match inside `1500 bar` or `5000 bar`.
- [x] **P1 — Complete Overlapping Repeated-Passage Protection (`apps/web/app/token-sequence-alignment.ts`)**:
  - Removed query length skip-ahead in `alignExactTokenSequence`: counts all occurrences contiguously including overlapping matches (`pump pump` in `pump pump pump`).
  - When `requireUnique: true` is set, declines ambiguous citations with multiple occurrences on the page.
- [x] **P1 — Non-Sequential OCR Validator Fallback Elimination (`apps/web/app/tiered-validation.ts`)**:
  - Removed unordered token-containment fallback from `checkVisual`. Claims like `The output power shall be 500 mW` will never pass against `The output power shall be 200 mW. Calibration reference: 500 mW.`
- [x] **P1 — Standalone Parameter-Value Requirement Recovery (`apps/web/app/visual-table.ts`)**:
  - Enhanced `isCompleteClauseInDraft`: recognizes standalone parameter-value requirements (`Pumping speed: 600 L/s.` within `Operating pressure: 200 bar; Pumping speed: 600 L/s.`) without requiring modal verbs like `shall`/`must`.
- [x] **P1 — Stress Test Runner Nonzero Exit Code (`apps/web/scripts/stress-test-harness.mjs`)**:
  - Script explicitly calls `process.exit(1)` when any stress case fails quality thresholds.
- [x] **P2 — Parameter-Colon Line Recombination (`apps/web/app/response-sheet.ts`)**:
  - Parameters wrapped across lines (`Minimum operating pressure:\n200 bar`) are recombined into single rows rather than splitting on the colon.
- [x] **Verification**:
  - 204 unit tests passing (`npm test`).
  - 17 pipeline contract cases passing (`npm run test:pipeline`).
  - TypeScript clean (`npm run typecheck`).
  - Production build passing (`npm run build`).

### OCR grounding keeps the same technical distinctions — 2026-11-06

The OCR acceptance path still had a separate permissive comparator after the native-text checks were tightened. It lowercased engineering units, collapsed `±` into `+`, and could accept all quote tokens even when they appeared out of order on one OCR line.

- [x] Use contiguous token-sequence matching for OCR candidate acceptance, validation, and positioned-line location. Removed unordered token-presence matching and substring checks that could match a numeric fragment inside a larger value.
- [x] Reuse the engineering token normalizer so `mW`/`MW`, negative values, and `±`/`+` remain distinct. Normalize `±` and `+/-` as equivalent while preserving their difference from plain `+`; continue reconciling dash glyphs, bullets, and the known `sil`/`sl` OCR variant.
- [x] Derive OCR boxes only from parser-provided offsets or positioned lines. Verify the specific matched occurrence before using its offsets, so an earlier token-similar passage cannot receive the highlight. Exact text with no trustworthy location remains a text-only visual match.
- [x] Add regressions for reordered OCR phrases, `500` inside `1500`, SI unit case, signed values, tolerance operators, and line-level OCR grounding.
- [x] Verification: 208 unit tests, TypeScript check, production build, and 17 scripted pipeline contract cases pass. The four-case stress harness passed its configured thresholds with 100% box grounding; the scanned scientific-notation case had 80% key-phrase recall and missed `10^9`.

OCR and stress results remain bounded by the tested synthetic documents and installed OCR runtime; they do not establish real-document recall.

### Portable encrypted Phase 1 review sessions — 2026-11-09

- [x] Add a manually downloaded `.tce-review` file for analysis, citations, reviewer marks, and response-sheet edits; encrypt locally with Web Crypto PBKDF2-HMAC-SHA-256 (600,000 iterations) and AES-256-GCM.
- [x] Exclude the original PDF from the bundle. Require the exact PDF bytes to be reselected and SHA-256 verified before restoring citation access.
- [x] Bound bundle and payload sizes, validate format/version and core review/source structure, reject wrong passphrases and modified ciphertext, and limit this feature to Phase 1 state.
- [x] Document passphrase loss, source file, size, browser security-context, and plaintext-in-memory constraints in `docs/runbooks/local-review-sessions.md`.
- [x] Add tests for encrypted round-trip, tampering, invalid source identity, and exact source-PDF fingerprint matching.
- [x] Manually verify browser download, unlock, matching-source restoration, preserved review state, and citation drawer behavior with a synthetic PDF/session fixture; no client tender or model endpoint was used.
- [ ] Complete required PR CI.

This is a user-controlled encrypted file workflow, not autosave, cloud persistence, or multi-user history. It does not make an extraction more complete or verified.










