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

### Reading dated implementation notes

The dated entries below preserve the sequence of implementation and investigation. They are historical snapshots, not a single description of current behavior. When entries conflict, the later relevant entry supersedes the earlier one; current source code and its regression tests are authoritative for shipped behavior.

### Additional adversarial audit sequence — 2026-11-06

The new audit identifies reliability work that supersedes the older deployment-first ordering. Address confirmed findings in this sequence: hybrid-page OCR; independent response decisions for separate obligations; access control and request quotas; visual-completion provenance; OCR confidence for numeric/operator tokens; long-cell spreadsheet clipping; source-page citations in exports; and queued model-request deadlines. Keep custom-domain DNS as an open release gate. These items change distinct safety or operational guarantees and should remain separate PRs.

The independent-response change supersedes the earlier 2025-10-25 response-capacity note where it says verified subpoints from one source cell should be reassembled into one response row. Every accepted, independently assessable split stays in its own response row with its own source requirement ID and blank OEM decision fields. Page continuations of one obligation and presentation headings may still merge. The existing 250-response-row limit applies after this projection and stops oversized analyses without partial output.

The unauthenticated-upload finding now has a production Basic-auth gate, with a fail-closed response when its password is missing. This does not implement a global quota or cross-instance concurrency limit; those remain open because the single-app MVP has no shared state store, and process-local counters would not provide a global guarantee on serverless deployments.

Model-proposed visual completions no longer replace source text in a requirement or export. The literal selectable quote remains the response text; a high-confidence completion is attached only as a visibly unverified suggestion in the source drawer. Human confirmation is still required before any wording is changed in the editable response sheet.

Local Tesseract parsing now retains per-word confidence and geometry. A line containing numeric values derives its confidence level from numeric/operator tokens and adjacent recognized engineering units, rather than letting high-confidence prose raise a weak technical value's average. When multiple technical values share a line, the lowest relevant token confidence controls the line-level review signal.

Excel export now splits long cell contents across bounded-height physical rows instead of capping one oversized row and clipping its tail. Continuation rows preserve the source wording in order and vertically merge the OEM response fields so the requirement still has one response decision. The spreadsheet regression test checks the generated worksheet values, row heights, and merged response field.

Sectioned DOCX and XLSX exports now include the existing locked source-page column, so recipients can trace requirements back to the tender. Printable PDF intentionally keeps omitting that column and its page-number footer, per the 2026-10-25 client clarification; the source page remains available in the review UI. Tests inspect the generated DOCX/XLSX content and preserve the PDF omission check.

Model calls now keep analysis cancellation active while waiting for a concurrency slot, then start their 90-second execution timeout only after admission. This prevents queue wait from consuming the provider's execution window; the regression test holds a request in the queue longer than the execution window's remaining time and verifies it still receives a fresh window. A separate wall-clock budget for the complete analysis is not added by this change.

### Evidence-first redesign sequence update — 2026-11-07

The additional adversarial audit was written against `c198300`, before PRs #309–316. Rechecking current `main` confirms its listed hybrid OCR, independent response rows, production access gate, visual-completion separation, value-level OCR confidence, long-cell Excel splitting, DOCX/XLSX page citations, and queue-timeout findings have each been addressed in separate PRs. Global per-user/tenant quotas and cross-instance concurrency remain open; this single-user app has no shared state, and a local in-memory limiter would not satisfy that guarantee. Printable PDF page citations remain intentionally omitted under the earlier user clarification; DOCX and XLSX include them.

The user's broader document-intelligence redesign changes the next-work sequence. Keep custom-domain DNS and hosted preview access as open release gates, but proceed with the evidence baseline and architecture before deployment work. The six-document parser/model run and partial human-adjudicated cases are recorded in `benchmarks/representative-tenders/`; the results show only 2 of 6 local analyses completed within the 295-second client limit and do not establish recall. One additional public tender baseline candidate is now recorded, but its gold annotation is also partial. The next implementation checkpoint is a complete source inventory and independently annotated golden/held-out set, followed by measured parser and extraction changes. The baseline remains incomplete and has no cost telemetry. See `docs/architecture/ADR-0001-document-intelligence-redesign.md` for the staged architecture decision and trade-offs.

A new IIT Guwahati geosynthetic UTM tender is now recorded separately as an additional public-source baseline candidate. The local model run completed in 288 seconds but selected only pages 6–11, left nine pages unaudited, and produced 114 rows all requiring human review. Manual comparison of the rendered page 11 found three missed after-sales/maintenance obligations. This is partial adjudication on one additional document, not an exhaustive held-out score. The PDF remains local and is not redistributed; its public source, hash, parser counts, run conditions, and golden cases are in `benchmarks/representative-tenders/heldout-*2026-11-07.json`.

The page inventory now records raster-image presence, whether OCR was recommended, whether it ran, and whether it found text, found no text, failed, or was skipped because of engine/page/time limits. Native text and OCR regions remain separate. Synthetic tests cover hybrid native-plus-OCR pages and distinguish each OCR outcome. This improves provenance reporting only; it does not detect image-region coordinates or change page routing/extraction behavior. The full source inventory and completeness audit remain open.

The inventory now captures approximate image-draw bounds from PDF.js graphics transforms, retains stable page-scoped region IDs, uses significant image regions with sparse native-text overlap as an additional whole-page OCR trigger, and overlays the approximate bounds in the source viewer. A synthetic hybrid-page test verifies bounds and OCR recommendation; a cross-parser check matched the first Saha page's two PDF.js regions against PyMuPDF bounds within rounding. Across the six PDFs, 48 regions were recorded on 42 pages and 23 pages were recommended for OCR versus 21 under the earlier page-only heuristic. The 5% area threshold avoided adding passes for the repeated small IISc header image; these trigger counts do not measure OCR accuracy or requirement recall. Small image regions and non-image visual content still need human inspection.

The six representative source PDFs are available locally and their fingerprints match `benchmarks/representative-tenders/manifest.json`. A page-level PyMuPDF shadow inventory now records metadata for all 183 pages without storing source text or coordinates. It independently confirms 13 image-only pages in the scanned Shah tender and native text on every page of the other five documents. This is useful page inventory evidence, not a semantic routing or extraction completeness result; region-level inventory and end-to-end per-page dispositions remain open.

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










