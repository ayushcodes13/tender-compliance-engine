# Tender Review MVP checkpoint

## Product scope

A single-user Next.js app demonstrates one meaningful AI engineering workflow:

```text
Upload a text-based tender PDF
→ extract technical requirement quotes
→ verify each quote against selectable text on its cited page
→ show that page and its bounding box
→ let a human mark it checked
→ download a DOCX with blank OEM response fields
```

This is a deliberate simplification requested by the user. The deployed product is one Next.js app. It has no separate API service, worker, database, queue, or Docker setup. Tender bytes and review state stay in browser memory; the PDF text is sent to the configured model during one bounded server action. The server-only model credential is never exposed to the browser.

## Checkpoint 72 — Single-user Vercel MVP

**Status: LOCAL MVP VERIFIED; HOSTING NOT YET VERIFIED.**

### Done only when

- [x] Only the Next.js app and its small local run scripts remain as runtime services; legacy API, worker, database, queue, and Docker setup are removed.
- [x] TypeScript check and optimized production build pass. A fresh dependency install was completed earlier in this work session.
- [x] Example 2 uploaded freshly and extraction succeeded through the app's configured model path: 102 source-matched requirements from 37 pages; 5 non-matching suggestions discarded.
- [x] Input 2 was uploaded freshly; visually legible text embedded as images in vector compliance-table cells is transcribed only at high model confidence, retained alongside the original selectable-text excerpt, and marked for human verification in the review UI. The generated response sheet includes the recovered phrases; a focused validator and regression tests guard selectable-word preservation.
- [x] Displayed requirements use unique literal quotes matched to selectable text on their cited pages; all start unreviewed. The PDF page and bounding-box overlay render in the browser.
- [x] A DOCX downloaded and was inspected: 102 tender rows, 102 page references, and 102 blank OEM response cells.
- [x] Desktop review layout was visually inspected; a reviewer mark changed the checked count from 0 to 1. Narrow layout rules are present; narrow-screen visual QA remains to be completed.
- [x] Extraction is scoped to technical requirement wording and quantified product specifications; commercial, delivery, procurement, and bid-response clauses are filtered out by a conservative rule screen.
- [ ] Vercel uses `apps/web`, server-only model settings, and `tender.devayushrout.me` is configured through Namecheap DNS and verified over HTTPS.
- [x] README and deployment runbook give accurate local steps and limits; hosted steps are documented but not yet verified against an authenticated account.

### Limits

- Scanned PDFs without extractable table structure remain unsupported. Visual transcription currently applies only to image text embedded inside detected vector compliance-table cells; it is not general-purpose OCR.
- Visually transcribed wording is a reviewer aid, not an exact selectable-text citation. The UI labels the warning and highlights the whole source row; a human must verify every character against the rendered PDF.
- One bounded synchronous extraction call; no background jobs or persistence.
- A validated quote and bounding box prove the displayed citation only, not exhaustive tender coverage.
- The technical-only rule screen can miss technical requirements and is not proof of complete coverage; review every source citation.
- Requirements remain in human review until the user checks them.
- The hosted workflow is not complete until a fresh hosted upload and DOCX export are inspected.
