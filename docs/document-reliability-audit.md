# Document reliability audit

Audit date: 2026-10-25. Scope: the active single-user Next.js Phase 1 application, based on `main` at `3adbc32`. No OEM assessment, supplier compliance verdict, database, queue, or new orchestration service is introduced.

## Client acceptance case

The reported failure concerns a 42-page tender, `FinalTenderDocument.pdf`. Its native text is selectable; it is not the scanned tender mentioned in earlier checkpoint notes. Physical PDF pages and printed numbers agree for the inspected technical section:

- Annexure I begins on page 20 and continues through page 22.
- Annexure II begins on page 23 and continues through page 26.
- Both contain equipment groups A–D. The optical-table group has 16 source rows in each annexure.
- The annexures differ in some wording and obligations. They must not be deduplicated into one supposed authoritative specification.
- The response sheet should keep equipment grouping, specification labels, literal descriptions, annexure context, and source citations. Serial numbers remain source evidence; the grouped export omits them. Compliance, deviation, and reviewer remarks begin blank.

The original tender and generated client artifacts remain local and are not committed as fixtures. Automated fixtures are synthetic contract cases, not client-approved gold labels.

## Audited application boundaries

| Boundary | Owning files | Finding / disposition |
| --- | --- | --- |
| Entry points and deployment | `app/page.tsx`, `app/new/page.tsx`, `app/api/analyze/route.ts`, `next.config.ts`, `scripts/pilot-*.sh`, `Makefile`, CI | Startup targeted the wrong directory; fixed. CI built without running regression tests; unit and production pipeline tests added. |
| PDF parsing / layout | `actions.ts`, `pdf-structure.ts`, `pdf-path-rectangles.ts`, `vector-table.ts`, `visual-lines.ts` | PDF.js could transfer the original byte buffer before fingerprinting. Pass a copy to the parser. Native text normalization is disabled to preserve encoded source characters. Node rendering uses traced PDF.js standard fonts and CMaps instead of host-installed fonts; a raster regression check guards blank text. Negative rectangle dimensions emitted by top-origin PDF generators are normalized. Existing vector geometry remains limited for transformed/rotated/malformed grids. |
| OCR | `local-ocr.ts`, `visual-ocr.ts`, OCR tests | Local Tesseract/Poppler adapters preserve approximate OCR evidence separately. Sparse native headers previously hid OCR text in routing; transcripts are now both supplied. Hosted OCR remains unavailable. Visual completions must preserve numeric signs/operators, decimal values, and unit case, not only word tokens. |
| Model access | `model-provider.ts` and tests | Bound model requests to three concurrent calls per analysis; queued cancellation is tested. Provider availability and latency remain external dependencies. |
| Routing | `page-routing.ts`, `extraction-route.ts`, `annexure-routing.ts`, `document-input.ts` | Live reruns omitted pages 22 and 26. Verified standalone source annexure headings now define boundaries; selected annexures retain their tails. Increase bounded routing excerpts and distinguish technical-bid instructions from actual specifications. |
| Extraction and source acceptance | `actions.ts`, `extraction-rules.ts`, `visual-table.ts` | A familiar-keyword filter rejected valid model-selected technical wording. Remove that second whitelist from model acceptance while retaining source validation and administrative screening outside source table rows. Distinct source row locations survive deduplication. A model header classification cannot discard a data row unless the source cells match the verified column headers. Blank specification cells retain their label citation and blank description; serials/responses are not promoted into specifications. |
| Table schemas and grouping | `column-layout.ts`, `table-columns.ts`, `response-sheet.ts` | A single document-wide layout cannot represent three-column specifications plus five-column compliance tables. Map tables independently, inherit the last verified map on continuation pages, and normalize the response projection. Unverified maps fall back to general extraction. |
| Mixed documents | `actions.ts`, `document-input.ts` | One non-table page previously changed extraction for all selected pages. Partition supported vector pages from general pages; bound general contexts by text and page count. |
| Provenance / coverage | `source-document.ts`, `coverage-ledger.ts`, UI and tests | Preserve fingerprint, version, physical page, source-cell identities, native offsets, and OCR distinction. Coverage counts describe detected rows and model actions; they are not recall estimates. Merged equipment headings spanning cells do not claim a single source-cell identity. Explicit lettered group rows with an empty specification cell remain headings even if the model calls them headers. |
| Review and transport | `tender-mvp.tsx`, `pdf-evidence-viewer.tsx`, `analysis-events.ts`, `analysis-stream.ts`, `processing-progress.ts` | Existing editable sheet, human check, cancellation, SSE and locked-page behavior retained. Group editing/merging respects annexure scope. Source links survive joined rows. |
| Export | `response-sheet.ts`, `compliance-format.ts`, DOCX/XLSX UI writers, `pdf-export.ts` | Reassemble subpoints into their source table row. Join verified adjacent-page continuations with both citations. Built-in PDF fonts corrupted comparison signs; embed licensed DejaVu Sans and round-trip-test signs/units. Unsupported glyphs stop PDF export rather than silently disappearing. |
| Presentation and docs | landing/dashboard/method routes, `app-shell.tsx`, `globals.css`, `DESIGN.md`, README, checkpoint/runbook/review notes | Historical removed Python-service test counts are not evidence for the current app. Mark them historical. No visual redesign is part of this change. |

## External research and engineering decision

The [Docling technical report](https://arxiv.org/abs/2408.09869) describes document conversion as layout analysis plus table structure recognition. This supports treating a table as source rows/cells rather than only a stream of model quotations. It does not establish that Docling or any parser will handle these client documents correctly. A Python/model conversion stack was not added to the deliberately single-app MVP in this change.

The [Langfuse dataset guidance](https://langfuse.com/academy/datasets) distinguishes repeatable inputs, expected outputs, and metadata. This change uses local deterministic contract fixtures with explicit assertions; it creates no live Langfuse dataset and does not call synthetic-label agreement model accuracy.

[Vercel documents a 4.5 MB function payload limit](https://vercel.com/docs/errors/function_payload_too_large). The app's 4 MB PDF bound remains. A single synchronous request still has hosting duration/memory constraints; chunked model input does not turn it into a durable background job.

## Verification record

- `npm --prefix apps/web test`: 134 tests pass, with no skips. Covers source/OCR distinctions, Unicode PDF round trips, long-row pagination, standard-font raster rendering, source-cell identity, operators/units, annexure boundaries, grouping, blank specifications, and cancellation.
- `npm --prefix apps/web run typecheck`: pass. `npm --prefix apps/web run build`: pass. `cd apps/web && npm run test:pipeline`: pass on the optimized production server with a scripted provider. Pipeline cases include an unfamiliar short clause, mixed prose and different table schemas, two 16-row equipment groups, independent omission recovery, invented values, invalid pages, and worksheet edits with locked citations. A deliberately incorrect model header label cannot hide the source data row.
- Fresh real-provider upload of the actual 42-page PDF in the production-mode browser: pages 20–26 retained, all eight A–D equipment headings present, and 93 response rows. A further real-provider production API run after standard-font bundling returned identical worksheet values. Candidate split counts varied; this is not an accuracy/recall measurement.
- Both annexures have 16 optical-table rows and 16 vibration-isolator rows; each compressor group has 5. The remaining group has 8 rows in Annexure I and 11 in Annexure II. The service continuation retains both pages 25 and 26.
- SHA-256 returned by the application matches the original upload bytes. Compare values against the actual local source file, not the historical empty-buffer fingerprint.
- Browser review/export checks: 93 rows, eight merged equipment groups, blank OEM fields, no editable source-page field; remove → 92 rows, reset → 93; reviewer mark toggled and restored; an explicit worksheet edit appears in all three exports. Afterward the original worksheet was restored and all reviewer checks left unconfirmed.
- Latest client layout: eight separate source tables with row counts 16/16/5/8 and 16/16/5/11. Both annexure labels and their literal source title lines appear above the relevant equipment headings and tables. Generic document titles, filenames, row-count introductions, annexure/equipment body columns, and printed page references are omitted.
- Excel: all 465 specification/response cells match the shared section projection; source headings occupy standalone rows. DOCX: eight tables with 93 data rows and five columns each; annexure/equipment headings are paragraphs outside tables. The document was rendered and all nine pages inspected. PDF: nine pages in the sectioned A4 layout; all 93 descriptions and signs/units remain, with no source-page column or numbered footer. Long rows stay together when they fit on the next page.
- Latest UI/export verification replays the real provider result through the normal upload UI to isolate presentation checks; it is distinct from the fresh live-provider extraction checks. Desktop review/source/table screenshots and a 390 px check are local. Document width equals viewport width at 390 px; the wide sheet scrolls inside its own container.
- Generated client artifacts, analyses, and screenshots are local only under `.local/client-review/` and `output/playwright/`. No client PDF, generated export, credential, or source screenshot is included in the PR.
- GitHub CI and hosted preview results are recorded separately on the PR. Local verification does not establish a hosted deployment or permit merging failing required CI.

## Remaining limits

- Source matching proves citation grounding, not extraction completeness or semantic correctness. A human must compare the whole source and review the group boundaries, splits, and OCR warnings.
- A selected annexure is expanded only when a standalone source heading is recognized in native text. Unlabelled sections, image-only headings, unusual reading order, and unseen layouts may need manual selection/review.
- Vector detection is not a general table-recognition engine. Borderless, transformed, rotated, merged, or malformed grids use fallback extraction and can still lose structure. Crop fallback may stop on incompatible column maps rather than mixing them silently.
- Local OCR is supported only with installed tools/languages; hosted Vercel OCR is unavailable. OCR transcript matches remain approximate visual evidence.
- The active review stays in memory; refresh clears it. No user authentication, tenant isolation, durable audit history, production upload scanning, or customer retention controls are claimed.
- The model provider, public deployment settings, DNS, and hosting limits need independent verification on the intended client environment. No production deployment is established by local checks.
- PDF font coverage is finite. The app refuses unsupported characters and directs the user to DOCX/Excel. A known private-use Symbol bullet is rendered as its visible bullet in PDF only; source evidence is unchanged.

## Source heading projection

The client clarified that annexure and equipment/table titles are headings, not repeated or merged data cells. `response-sections.ts` now projects the editable review state into source-ordered sections shared by the UI and printable writers. It retains source identities and citation fields in the underlying state while presenting them separately. Native title lines between a verified annexure heading and its first table are retained only when they match the PDF transcript. Header wording is taken from the per-table verified column map. Repeated table titles remain distinct when their source heading IDs differ; mixed narrative pages do not inherit the preceding equipment heading accidentally.

Browser checks on the revised layout confirm eight tables, 93 rows, headings outside each table, 93 UI citations, correct edit column mapping, remove/reset behavior, and normal downloads. These presentation checks replay the prior live extraction with title lines read directly from the actual PDF through the same native heading helper. The updated production contract test separately verifies that native title lines flow through fresh API analysis.
