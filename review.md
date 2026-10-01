# review.md — items needing your input

> For anything marked 🟢 I'll proceed with the stated default. Anything 🔴 is a
> blocking decision — add your preference and I'll adjust the next checkpoint.
> I (the agent) will note which default I shipped so you can override per-checkpoint.

## CP20 — Rendered page assets  ✅ DONE (PR #25, merged)
- Default shipped: PyMuPDF @ 150 DPI PNG, deterministic UUID5 storage keys, best-effort
  non-fatal, encrypted PDFs -> fatal. `create_worker` injects `PymupdfRendererAdapter`.

## CP21 — Scanned-page detection and OCR  🟢 proceeding
- Page detection (`ocr_needed`) already wired by CP19 parser (pypdf flags pages with no
  native text). CP21 adds the OCR provider itself.
- **Provider default shipped:** Tesseract (local `tesseract` binary) via `pytesseract`,
  plus a deterministic `FakeOcrAdapter` used by every test. `create_worker` injects
  `TesseractOcrAdapter`, degrading to "no OCR" (best-effort) if the binary/import is
  absent — it never blocks worker startup.
- Real-OCR unit tests skip gracefully when the Tesseract binary is absent (CI is
  ubuntu-latest without the binary), so CI stays green; the fake exercises all
  character-set / scan-vs-native / mixed logic.
- **Production note for you:** a real deployment needs the `tesseract-ocr` system
  package installed on the worker host (not a Python dep). If you'd prefer a cloud OCR
  provider (AWS Textract / GCP Vision / Azure) instead, tell me and I'll swap the
  adapter — the `OcrAdapter` port is provider-agnostic.

## CP22 — DOCX adapter  ✅ DONE (PR #27, merged)
- Default shipped: `python-docx`. DOCX walked in body order (paragraphs + tables
  preserved), surfaced as a single text segment because `.docx` has no inherent page
  count — `ocr_needed=False` (native text), per-page provenance warning, no fabricated
  page numbers. Routed via a new `CompositeParserAdapter` (PDF→pypdf, DOCX→python-docx);
  processor now records the **sub-parser** name on the version (`"python-docx"`/`"pypdf"`).
- 🟡 CP23 input optional: I did NOT split DOCX on explicit `<w:br w:type="page">` breaks
  (deferred for page-count honesty). If you want real per-page DOCX segments, tell me and
  I'll add explicit page-break detection in CP23; otherwise I'll keep the single segment
  until a docx→PDF preview/derive step exists (CP23/CP36).

## CP23 — DocumentPage structural cleanup  ✅ DONE (PR #28, merged)
- New `parser/cleanup.py` (`cleanup_pages`, pure): strip repeated identical header/footer lines
  (recurrence across ≥max(2, 50%) of pages, short, non-clause-numbered) into a NEW
  `cleaned_text` column (migration `0008`); raw `extracted_text` is never mutated.
  `store_pages` records `headers`/`footers`/`warnings` in `structural_metadata`.
  Deferred (no input needed): full clause/numbering hierarchy + cell-level table
  structure → CP25–CP27. Single-segment DOCX page-boundary question (from CP22) still
  open for your review — see above.

## CP24 — Retry, idempotency, partial failure  🟢 proceeding (planned)
- Per-stage retries, deterministic job IDs (already UUID5), partial-failure handling.

## CP25–CP30 — Extraction pipeline + deterministic numeric parsing  🟢 proceeding (planned, later)
- **Default shipped:** OpenAI `gpt-4o` as the LLM provider (via an `LlmAdapter` port) with a
  deterministic `FakeLlmAdapter` for tests. Will surface in CP26.

## CP36 — Source viewer  🟢 proceeding (default shipped)
- CP21 produces per-page PNGs (CP20). The web "source viewer" needs to render these.
- Options: (a) serve the stored PNG bytes through the API (fast, no client deps), or
  (b) integrate PDF.js for native-PDF viewing alongside OCR text overlay.
- **Default shipped:** (a) serve stored page PNGs with OCR/native text overlay via the
  API. The API exposes page images by `/projects/{pid}/documents/{did}/versions/{vid}/pages/{page_num}/image`,
  page text, and source anchors (bbox, page, clause) for highlighting. The web viewer
  renders the PNG and overlays rectangles from source anchors. If you prefer (b) PDF.js,
  tell me and I'll swap the rendering layer — the source-anchor data is format-agnostic.
- **No input needed** unless you want PDF.js instead of PNG serving.

## CP41–CP42 — Matrix + XLSX export  🟢 proceeding (planned)
- Default shipped: `openpyxl`. Matrix projected from reviewed requirements; XLSX export
  with source citations per row.

## CP26 — LLM extraction adapter, prompt versions, run metadata  🟢 proceeding (shipped)
- **Decision:** OpenAI `gpt-4o` is the production default provider (matches CP25–CP30 entry), routed through the `LlmAdapter` port.
- **Decision (safety/cost):** The `openai` package is a *lazy* dependency — imported only inside `OpenAiLlmAdapter._client()`. It is **NOT** added to `pyproject.toml` dependencies, so CI/tests never require it and `create_worker` never fails without it. A real extraction call requires `OPENAI_API_KEY` + the package at call time (not startup).
- **Decision (no surprise cost):** The live OpenAI test is opt-in only (`CP26_OPENAI_REAL_CALL=1` env); CI always skips it (no key, no env flag). The `extraction_runs` audit table records cost/tokens as NULL when unknown (never fabricated 0), per the LLM cost-logging SOP.
- **No input needed** unless you want a non-OpenAI default provider; I left `openai_base_url` configurable for Azure/Switchpoint-style endpoints.

## CP27 — Chunking, overlap, clause hierarchy, tables, multi-page windows  🟢 proceeding (shipped)
- No decisions needed. Pure in-memory chunker (no DB change).
- Defaults shipped: `max_chars=1500`, `overlap_chars=150` (validated `overlap < max_chars`). Clause-table boundaries reuse `parser.cleanup`'s numbered-clause regex; tables kept atomic.
- `openai` not needed here (pure Python, deterministic). No input needed.

## CP31 — Extraction diagnostics and reconciliation history  ✅ DONE (PR #36, merged)
- Default shipped: one `extraction_diagnostics` row per EXTRACT run (unique on
  `processing_run_id`) with aggregate counts (windows/calls/candidates,
  accepted/rejected/deduped/promoted/ocr_warning), provider/model/prompt/schema
  versions captured from the audited LLM calls, a rejection-breakdown JSON
  (reason-code → count, never document bodies), and the CP29 reconciliation
  summary JSON. `compute_diagnostics` is a pure function (no DB/IO). Re-running
  a version = new run = new row (append-only history; never overwrites).
- No input needed. CP31 retry semantics kept as deferred (new-run-per-attempt).
