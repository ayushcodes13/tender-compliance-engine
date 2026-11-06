# ADR-0001: Evidence-first document intelligence redesign

- Status: accepted for incremental implementation
- Date: 2026-11-07
- Scope: Phase 1 tender intake, requirement extraction, human review, and export

## Context

The application is a single Next.js/TypeScript service. `apps/web/app/actions.ts` owns most of the upload pipeline: PDF validation and parsing, page/OCR preparation, section routing, table interpretation, model calls, coverage accounting, quote verification, and response-sheet construction. The modules around it provide useful boundaries, but the orchestration remains broad and in-process. Browser state holds the uploaded document and review edits; there is no database, worker, shared queue, or cross-instance rate limiter.

PDF.js is the production parser. It supplies selectable text, positioned text items, page geometry, and vector drawing operators. `source-document.ts` preserves the document fingerprint, page-local text blocks, source references, and selected table structure. `vector-table.ts` reconstructs rows and cells from drawing geometry. `local-ocr.ts` uses Poppler rendering and Tesseract when available; `ocr-routing.ts` flags likely mixed/scanned pages. Layout interpretation and requirement classification use the configured model. Deterministic code verifies source text and locations, tracks extraction/coverage states, and projects independently answerable rows into review and exports. The model is not the source of citation geometry or verified text.

This design has produced useful capabilities, but a six-document run on `dd0c2c7` completed only two analyses within the local 295-second request limit. Routing also left many pages unaudited. A response matrix with source-matched rows therefore does not establish document completeness.

## Decision

Keep the product in TypeScript and retain PDF.js as the production parser while the redesign is measured. Evolve the existing pipeline through small, testable boundaries instead of replacing the application wholesale.

Treat a tender as a canonical, source-preserving inventory before interpreting it. The inventory should retain source document/version identity, physical page, exact text or OCR transcript, text and cell geometry when known, table candidates, OCR confidence, and unknown/approximate markers. Interpretation creates atomic requirement proposals that point back to inventory regions. Independent deterministic checks then measure grounding, completeness, numeric fidelity, and recoverable omissions. A human-reviewed requirement set projects into the editable response matrix and its exports without combining independent response decisions.

Requirement citations carry stable page-scoped source element IDs in addition to offsets and locations. Native text references link every parser text block overlapped by the exact source span; table references link the table, row, and cell; OCR references link only OCR regions containing an exact transcript match. A visual transcription without a deterministic text-to-region match keeps its geometric evidence approximate and does not receive a fabricated text element link. These are parser element IDs, not semantic paragraph/list/section IDs; hierarchy reconstruction remains a separate open step.

Before routing, the current runtime builds detected vector-table row candidates for every page with supported vector geometry, then checks the assembled source inventory for every physical page in order, exact native text-block offsets, unique parser element IDs, valid OCR-to-image references, and consistent table/row/cell relationships. Successful analyses expose this as a structural inventory check in the review ledger. Table geometry remains heuristic and may miss or combine tables; this gate detects malformed or incomplete parser output, not whether all visual regions, paragraphs, tables, or technical obligations were recognized.

The page-routing pass may also propose cross-section inconsistencies, such as different equipment subjects in a tender title and a compliance annexure. A deterministic boundary checks each quoted side against its claimed page transcript before surfacing a warning; verified proposals mark and route both pages for review without choosing an authority. The detector is model-assisted and sees bounded page-group excerpts, so it is not an independent consistency oracle and can miss conflicts across groups or outside the supplied excerpts. The Saha example is recorded as unresolved evidence, not as a live-model detection result.

The upload stream now enforces a 270-second wall-clock deadline, below the route's 300-second platform limit. On expiry it aborts work through the existing request signal and emits an explicit incomplete terminal error; it never returns already accumulated rows as a finished response sheet. This bounds one request and prevents a platform timeout from silently looking like success. It is not resumable processing: completed batches are not persisted, and the reviewer must retry a shorter tender. A future resumable design must checkpoint source-linked batch results and preserve per-page/audit completeness states before it can safely return partial work.

The vector-table coverage ledger also carries each detected row's table/row/cell IDs and the IDs of accepted requirements linked to that row. The link status reports only whether any accepted requirement is associated with the row; candidate and accepted requirement counts remain visible as separate counts. This join exposes source association and rejected candidates; it does not decide that a row containing multiple obligations is semantically complete.

Detected vector-table rows retain an advisory structural class and a reason code. Rows the classifier marks ambiguous do not generate requirements; they remain visible in the coverage ledger with their source text and an explicit unresolved classification. Header/instruction exclusions are likewise visible as source rows with their class and reason. These labels guide human review and are not ground truth; a linked requirement still does not prove that every obligation in a row was extracted.

The next engineering steps are:

1. Make inventory construction explicit and independently inspectable, retaining native text, OCR regions, raster image regions, and page geometry for hybrid pages. The current step records approximate PDF.js image draw bounds and exposes them for human page review; semantic region classification and canonical section/paragraph/list relationships remain open.
2. Compare the current PDF.js/vector reconstruction with optional parsers on adjudicated regions, not aggregate table counts alone.
3. Rework extraction around bounded, resumable page/region batches and explicit incomplete states; the current stream-level deadline stops overlong work but cannot resume it or return partial results.
4. Represent each independently answerable obligation as an atomic proposal and preserve all source locations through review and export.
5. Add independently annotated golden and held-out tenders before changing parser defaults or claiming improved recall.

## Parser evaluation and licensing

PyMuPDF 1.26.5 was run in shadow mode on the six local samples. Its `lines` candidate counts were broadly similar to the current vector detector on several documents and differed substantially on the Indore sample. Its `text` strategy generated table candidates on nearly every text-bearing page, which illustrates why raw candidate count is not a quality metric. The scanned Shah sample had no native text for PyMuPDF to recover. These results do not establish precision or recall, and do not justify switching production parsers.

Do not add PyMuPDF as a product dependency in this ADR. [PyMuPDF's licensing documentation](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright) describes its AGPL and commercial Artifex licensing options; adoption requires a licensing decision in addition to measurable gains on representative, adjudicated layouts. Evaluate Docling or other parsers under the same held-out, source-linked protocol before adding them. Keep parser experiments optional and isolated from runtime dependencies.

## Guarantees and boundaries

- Preserve source text and OCR as distinct evidence. OCR never silently overwrites the native transcript.
- Unknown page, clause, cell, confidence, or geometry values stay unknown; approximate coordinates remain labelled approximate.
- Keep independent obligations independently answerable. Only verified continuations of one obligation and presentation headings may merge.
- Evaluate source grounding, extraction completeness, and response/export fidelity as separate guarantees.
- Keep Phase 2 OEM ingestion, retrieval, compliance assessment, contradiction resolution, and submission generation out of scope.
- Do not claim unattended customer-ready output based on selected-page extraction or a partially completed run.

## Consequences

The current TypeScript runtime and local OCR tools remain in place while evidence is gathered. More explicit inventory and batch contracts will require incremental refactoring of `actions.ts`. The single-user deployment still lacks a cross-instance quota; process-local counters would not provide a global guarantee. A future shared-state or deployment-level control must be chosen before representing global spend limits as implemented.

The baseline and first adjudicated cases are tracked in [`../../benchmarks/representative-tenders/README.md`](../../benchmarks/representative-tenders/README.md). They are a starting subset, not a full benchmark or an unbiased held-out evaluation.
