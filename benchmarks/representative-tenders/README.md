# Representative tender baseline and new public sample

This directory records a local, source-linked baseline for six real tender PDFs. The PDFs remain outside the repository. `manifest.json` records their SHA-256 fingerprints, page counts, sizes, and local path hints so the owner can reproduce the run without committing source files. `baseline-2026-11-07.json` records parser-shadow counts and actual model-run outcomes at commit `dd0c2c7`.

The follow-up `heldout-manifest-2026-11-07.json` and `heldout-results-2026-11-07.json` add an IIT Guwahati tender acquired directly from the institute's public tender page. It was not part of the original six-document sample. The source PDF is not stored in Git. `heldout-golden-v0.1.json` records three page-11 omissions found by comparing the first completed run with the original page. This is one new sample, not a statistically sufficient holdout set; future work that uses these cases for tuning must not report them as untouched test data.

`heldout-page-dispositions-2026-11-07.json` records an assistant-reviewed page-level disposition for all 15 IIT Guwahati pages after reviewing selectable text and rendered page images. It distinguishes technical specification pages, documentary/service obligations, operational or contractual terms, bidder forms, and guarantee templates. The page labels are not yet human-adjudicated. `heldout-golden-v0.2.json` enumerates seven assessable obligation groups on page 11 with parser-reported bounds; three are recorded as missed, and four are reported present in the earlier summary. Exact positive output rows and source links were not retained, so the positive matches are not re-verified. Technical pages 6–10 remain unenumerated and the earlier extraction run's nine pages outside its omission audit are still not recall-evaluated. The PDF remains local and is not redistributed.

`page-inventory-shadow-2026-11-07.json` adds one record per page from the six available PDFs: page dimensions/rotation, native text character/word/block counts, embedded image-region count and approximate covered-area ratio, vector drawing count, and table-candidate counts by PyMuPDF strategy. It contains no tender text or source coordinates. It is a parser-side inventory diagnostic, not the production PDF.js inventory and not a semantic relevance or OCR-quality score. On this run, all 183 pages were represented; the scanned Shah tender had 13 image-only pages and the other five PDFs had native text on every page.

`source-region-inventory-shadow-2026-11-07.json` extends that diagnostic with parser-reported page-point bounds and stable IDs for 3,337 native text blocks and 48 embedded image draws, plus 376 table candidates across the three PyMuPDF strategies. It contains no source text. Line-based table candidates include cell bounds; the exploratory `text` strategy retains only table bounds and row/column counts because its broad candidates would otherwise dominate the artifact. Text-block order is the parser's block order, not a verified reading order. These geometries are not production PDF.js coordinates, verified citations, OCR regions, or semantic requirement labels. The artifact is an inspection aid for later independent annotation; all 183 pages still need a human disposition.

## Reading the baseline

The six documents contain 183 PDF pages. The current PDF.js/vector-table path and PyMuPDF `find_tables` strategies were compared in shadow mode. Counts are candidate geometry statistics only; they do not measure correct table detection. No OCR was run in the PyMuPDF comparison. The Shah document is image-only and therefore has no selectable text for either parser to interpret without OCR.

The configured local model path completed 2 of 6 analyses within a 295-second client limit. Three calls reached that limit while extracting, and the scanned Shah run failed at the application time limit. The two completed matrices are not recall results: many pages were not selected or omission-audited. The captured outcomes contain no cost telemetry. Do not use these results to claim quality or production capacity.

## Adjudicated source cases

`golden-v0.1.json` contains a small manually inspected subset from IISc Diamond Scriber and IIT Indore Geosynthetic UTM. It includes missed obligations, a merged set of independent bullets, a conflicting numerical specification, contextual language that should not be promoted into a universal requirement, and administrative form text. It is an issue seed, not an exhaustive annotation of either tender. The original PDFs and full model candidate text are not included here.

Before any quality claim, annotate every expected obligation on each selected tender, including source page/region, independent-answerability, exact value/unit/operator, modality, and disposition. Add separate unseen tenders with native-text, scanned, and hybrid layouts; do not reuse these six as a held-out set after iterating on them.

## Reproduction notes

- PDF.js and the production vector-table parser are in `apps/web`; run the repository's documented Node test/runtime commands with the pinned lockfile.
- PyMuPDF 1.26.5 was installed only in the local evaluation environment; it is not a runtime or development dependency of the product.
- Re-run the PyMuPDF shadow inventory with `python3 benchmarks/scripts/pymupdf-shadow.py id=/absolute/path/to/file.pdf ...`. It emits fingerprints, timings, parser counts, and source-region geometries, but never source text. Use the same version when comparing recorded results.
- For the IIT Guwahati sample, fetch only from the `sourceUrl` in `heldout-manifest-2026-11-07.json` into a private local path, verify the SHA-256 before use, then pass it to the same shadow script. Do not put the PDF or its full text in Git.
- The model run used the configured local provider, whose secret is deliberately not recorded. The 295-second client limit is part of the run conditions, not a provider SLA.
- Do not commit source tenders, full extracted document text, credentials, or provider request/response dumps.

## Limitations

The set is small and convenience-sampled, not statistically representative. The gold annotations are partial and manual. The original six-document model run timed out or failed on four documents, does not include token/cost telemetry, and cannot support a recall comparison. The IIT Guwahati analysis completed but nine pages were not omission-audited and all 114 output rows require human review. The public source did not state a reuse license; the source PDF is therefore kept local and not redistributed. More independent public tenders and a complete annotation protocol remain necessary.
