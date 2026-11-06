# Representative tender baseline

This directory records a local, source-linked baseline for six real tender PDFs. The PDFs remain outside the repository. `manifest.json` records their SHA-256 fingerprints, page counts, sizes, and local path hints so the owner can reproduce the run without committing source files. `baseline-2026-11-07.json` records parser-shadow counts and actual model-run outcomes at commit `dd0c2c7`.

## Reading the baseline

The six documents contain 183 PDF pages. The current PDF.js/vector-table path and PyMuPDF `find_tables` strategies were compared in shadow mode. Counts are candidate geometry statistics only; they do not measure correct table detection. No OCR was run in the PyMuPDF comparison. The Shah document is image-only and therefore has no selectable text for either parser to interpret without OCR.

The configured local model path completed 2 of 6 analyses within a 295-second client limit. Three calls reached that limit while extracting, and the scanned Shah run failed at the application time limit. The two completed matrices are not recall results: many pages were not selected or omission-audited. The captured outcomes contain no cost telemetry. Do not use these results to claim quality or production capacity.

## Adjudicated source cases

`golden-v0.1.json` contains a small manually inspected subset from IISc Diamond Scriber and IIT Indore Geosynthetic UTM. It includes missed obligations, a merged set of independent bullets, a conflicting numerical specification, contextual language that should not be promoted into a universal requirement, and administrative form text. It is an issue seed, not an exhaustive annotation of either tender. The original PDFs and full model candidate text are not included here.

Before any quality claim, annotate every expected obligation on each selected tender, including source page/region, independent-answerability, exact value/unit/operator, modality, and disposition. Add separate unseen tenders with native-text, scanned, and hybrid layouts; do not reuse these six as a held-out set after iterating on them.

## Reproduction notes

- PDF.js and the production vector-table parser are in `apps/web`; run the repository's documented Node test/runtime commands with the pinned lockfile.
- PyMuPDF 1.26.5 was installed only in the local evaluation environment; it is not a runtime or development dependency of the product.
- Re-run the PyMuPDF candidate counts with `python3 benchmarks/scripts/pymupdf-shadow.py id=/absolute/path/to/file.pdf ...`. The script emits fingerprints, timings, and counts only; it never prints extracted document text. Use the same version when comparing recorded counts.
- The model run used the configured local provider, whose secret is deliberately not recorded. The 295-second client limit is part of the run conditions, not a provider SLA.
- Do not commit source tenders, full extracted document text, credentials, or provider request/response dumps.

## Limitations

The set is small and convenience-sampled, not statistically representative. The golden annotation is partial and manual. The model run timed out or failed on four documents, does not include token/cost telemetry, and cannot support a recall comparison. Public held-out tender collection and reuse terms remain to be established.
