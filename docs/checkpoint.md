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

## Checkpoint 72 — Single-user Vercel MVP

**Status: LOCAL UI AND GPT-6 LUNA SMOKE VERIFIED; PUBLIC VERCEL APP REACHABLE BUT MODEL CREDENTIALS ARE MISSING; CUSTOM DOMAIN DNS IS UNRESOLVED.**

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

**Status: LOCAL ACCEPTANCE VERIFIED; REMOTE CI / RELEASE GATE PENDING.**

- [x] Real 42-page client PDF routes both full technical annexures, including continuation pages 22 and 26.
- [x] Different table column layouts preserve literal source specifications/descriptions. Source annexure labels/title lines and equipment headings sit above separate tables, with no annexure/equipment columns in the body; the optical-table group has 16 source rows per annexure. Source citations remain available in the UI.
- [x] Page continuations and source-cell subpoints retain their complete text and every source link when joined for export.
- [x] SHA-256 provenance matches the uploaded bytes after PDF.js parsing; unknown evidence remains unknown.
- [x] PDF export preserves comparison signs, numerical precision, and units. Per the 2026-10-25 client clarification, the printable PDF omits the source-page column and page-number footer; locked source citations remain available in the UI.
- [x] Regression tests, production build, and deterministic upload-to-sheet contract checks pass and run in CI.
- [x] Real browser upload/review and DOCX/PDF/Excel download are inspected, with remaining limits documented.

This checkpoint does not establish exhaustive extraction on unseen layouts, hosted OCR support, client production access controls, persistence, or a completed hosted deployment. See `docs/document-reliability-audit.md` for the evidence and limits.

- [ ] Required remote CI passes. Keep this checkpoint title open until the PR checks pass; do not merge a failing required check.

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
