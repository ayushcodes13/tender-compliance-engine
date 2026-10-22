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

**Status: LOCAL UI VERIFIED; CURRENT GPT-6 LUNA ENDPOINT UNREACHABLE FROM THIS MACHINE; HOSTING NOT YET VERIFIED.**

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
- [ ] Vercel uses `apps/web`, server-only model settings, and `tender.devayushrout.me` is configured through Namecheap DNS and verified over HTTPS.
- [x] README and deployment runbook give accurate local steps and limits; hosted steps are documented but not yet verified against an authenticated account.
- [x] GPT-6 Luna is the sole model provider; credentials are server-side and no Ollama/open-source model fallback is configured.
- [x] The server builds a source-preserving document model with a SHA-256 fingerprint, physical PDF page numbers, original PDF.js page text, text-block offsets and page-coordinate boxes. For selected vector-table pages it also retains row/cell geometry and identity. Accepted requirements carry a document/version reference; unique native-text matches include the original page excerpt and page-local offsets, while unmatched quotes do not become source excerpts. Visual transcriptions keep native context, OCR text, confidence, and approximate location separate. Printed page numbers remain unknown when the parser cannot determine them.
- [x] A single editable response sheet is not built when selected compliance pages expose different column headers or roles. Page-specific model column proposals must match literal source text, and visible maps must agree before they can share one sheet; incompatible or unsupported maps stop with a review message.
- [x] Successful model-routed reviews include a page-level coverage ledger: routing input/clipping, extraction state, known vector-table row counts and dispositions, candidate suggestions, source-matched rows, reviewer workload, rejection reasons, OCR-needed pages, and whether an omission audit ran or returned possible gaps. Up to twelve detected vector-table rows per page show their source-cell text, candidate count, accepted source-match count, and row highlight; excess findings remain included in the total and are disclosed. Rows without candidates or with fewer accepted matches than candidates are marked for inspection. The UI labels these as needing inspection, since an unmapped row can be a heading or other non-requirement content, and labels a model audit result as advisory rather than proof of completeness.

### Limits

- Scanned PDFs without selectable text and usable source structure remain unsupported. Visual transcription currently applies only to image text embedded inside detected vector compliance-table cells; it is not general-purpose OCR.
- Visually transcribed wording is a reviewer aid, not an exact selectable-text citation. The UI labels the warning and highlights the whole source row; a human must verify every character against the rendered PDF.
- One bounded synchronous extraction call; no background jobs or persistence.
- A validated quote and bounding box prove the displayed citation only, not exhaustive tender coverage.
- Grid-based row separation depends on vector border geometry. When borders are merged, missing, or malformed, the model-driven fallback and human review remain necessary; neither guarantees exhaustive coverage.
- A layout mismatch is detected only when the page model reports visible column headers. Continuation pages without headers inherit the selected schedule layout; unseen layout changes on such pages can still require human review.
- The omission audit currently runs only on the crop-based compliance-table path. Other extraction paths say the page audit was not run. Vector-row counts are known only where supported table geometry was detected; unstructured text has candidate counts, not a deterministic source-row denominator.
- Row-level coverage findings are available only where vector table geometry produced source rows. The UI lists the first twelve such rows per page; it gives a total and count of detected rows not listed for pages with more than twelve.
- Model routing and extraction can miss technical requirements and are not proof of complete coverage; review every source citation.
- Requirements remain in human review until the user checks them.
- The hosted workflow is not complete until a fresh hosted upload and DOCX export are inspected.
