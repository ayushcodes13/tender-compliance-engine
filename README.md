<div align="center">
  <img src="apps/web/public/tce-mark.svg" alt="Tender Review mark" width="88" height="88" />

  <h1>Tender Review</h1>

  <p><strong>Turn tender PDFs into source-linked OEM response sheets.</strong><br />
  Review each candidate against its original page, then export the tender wording with blank supplier response fields.</p>

  <a href="https://tender-compliance-engine.vercel.app/"><img alt="Live demo" src="https://img.shields.io/badge/LIVE%20DEMO-Vercel-0b3d91?style=for-the-badge&logo=vercel&logoColor=white" /></a>
  <img alt="Next.js 15" src="https://img.shields.io/badge/Next.js-15-111827?style=for-the-badge&logo=next.js&logoColor=white" />
  <img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-5-3178C6?style=for-the-badge&logo=typescript&logoColor=white" />
  <img alt="Single-user MVP" src="https://img.shields.io/badge/Single--user-MVP-526581?style=for-the-badge" />

  <br /><br />

  <a href="https://tender-compliance-engine.vercel.app/">
    <img src="docs/screenshots/readme-dashboard.jpg" alt="Tender Review dashboard showing the review workflow and recent reviews area" width="100%" />
  </a>
</div>

## What it does

Tender Review is a focused single-user demo for preparing a technical response sheet from a text-based tender PDF. It finds candidate clauses, links each candidate to selectable text on its cited page, displays a page highlight, and exports a DOCX with blank OEM response fields.

Selectable vector tables are read by source row and cell geometry. The model maps each table's visible headers and identifies equipment groups; continuation pages inherit the last verified map. The response preview and exports place the source **annexure label, title lines, and equipment/table headings above separate tables**. Table bodies contain the source specification labels and descriptions plus blank compliance, deviation, and remarks fields. Source page references stay locked in the UI for validation and are omitted from these printable tables. Serial numbers remain in source evidence. Split review candidates from the same source cell are reassembled in the exported row, while the two annexures remain separate even when wording repeats.

A standalone source annexure heading establishes a page boundary. When the model selects part of that annexure, its remaining pages are included up to the next verified annexure heading so short service/warranty continuations are not silently dropped. Pages without usable table geometry use bounded text/image extraction and an advisory omission audit. A source match verifies a citation, not complete coverage.

The local review accepts up to 250 verified response-sheet rows per run. The limit is checked after source verification and source-cell reassembly; rejected model suggestions do not count, and an oversized sheet stops explicitly instead of returning a truncated result.

The app does not decide whether a supplier complies. Every candidate starts in **Needs review** and should be checked against the original tender.

## Screenshots

The screenshots below are real captures from the hosted MVP. The review example uses a sample PDF and shows the currently deployed **rule-based preview**. Its candidate list can include false positives and can miss requirements; the count is not a completeness measure, and the example rows have not been approved by a reviewer.

<p align="center">
  <img src="docs/screenshots/readme-review-evidence.jpg" alt="Review workspace with a source-matched candidate, cited tender page, and bounding-box highlight" width="100%" />
</p>

The yellow page highlight is positioned from the matched source text. Selecting a candidate opens its citation and quote; the reviewer can compare both with the original page before marking it checked.

## Try the hosted demo

Open [Tender Review on Vercel](https://tender-compliance-engine.vercel.app/). Upload a readable, text-based PDF (up to 4 MB and 120 pages), choose a candidate, inspect its citation and page highlight, and download the response sheet.

For a no-cost, larger-upload preview configuration, see [Free preview hosting](docs/runbooks/free-preview-hosting.md). It targets Render's Free Node/Docker service and is not deployed by this repository. Render's inbound request cap must be verified on the actual free host before claiming 32 MB hosted acceptance. Vercel's existing function payload limit remains 4.5 MB.

GPT-6 Luna routes tender pages and proposes requirement candidates. Candidate quotes are checked against selectable source text before display; the model key remains server-side.

## How a citation is produced

```text
Tender PDF
   ↓
Read selectable text and PDF page geometry
   ↓
Group supported technical table cells, or choose candidate quotes
   ↓
Tie each row or quote to its cited page and geometry
   ↓
Show the source row or quote and highlight for human review
   ↓
Export source wording and blank compliance/remarks fields to DOCX
```

PDF.js reads the PDF text and provides the page-coordinate geometry used by the highlight overlay. Quotes that cannot be matched to the cited page with usable geometry are not presented as verified citations. A visible source match still does not prove that the whole tender has been covered.

## Run locally

Prerequisites: Node.js 22.13+, npm, and GPT-6 Luna credentials configured in the local environment. For local scanned-page OCR, install Tesseract 5 with the configured language data; OCR is optional for text-based PDFs.

```sh
git clone https://github.com/ayushcodes13/tender-compliance-engine.git
cd tender-compliance-engine
cp .env.example .env.local
make web-install
make pilot-start
```

The app uses GPT-6 Luna for model-assisted extraction. Set `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL=gpt-6-luna` in `apps/web/.env.local`. Tender text and page images are sent to the configured endpoint for processing. There is no Ollama or open-source model fallback. Structured source tables with explicit cell geometry may be grouped directly from the PDF without an LLM call.
For production, set a strong `APP_ACCESS_PASSWORD` environment variable in the deployment before opening access. The app requires HTTP Basic authentication (username `tender`) on every page and API route, including `/api/analyze`. Production traffic fails closed with a configuration response if the password is unset. Local development remains open when the variable is absent; set it locally to exercise the same login challenge. Store this password only in the deployment's secret manager, never in the repository.
For a local macOS setup, install Tesseract 5 and Poppler's `pdftoppm` tools with `brew install tesseract poppler`. Tesseract and its trained data use Apache-2.0; Poppler is an optional external renderer under GPL terms and is not bundled by this project. The app detects standard Homebrew paths and `PATH`; set `TESSERACT_BINARY` or `PDFTOPPM_BINARY` in `.env.local` if either executable is installed elsewhere. `TESSERACT_LANG` defaults to `eng`; set it to a `+`-separated language list such as `eng+hin` only after installing each matching trained-data file. OCR text stays separate from native PDF text, carries approximate page boxes and Tesseract confidence, and every OCR-derived requirement remains marked for human verification. The hosted Vercel preview does not bundle these local binaries and reports scanned documents as unsupported there.
Open [http://127.0.0.1:3307](http://127.0.0.1:3307). Stop the local app with:

```sh
make pilot-stop
```

## Architecture

The hosted MVP is one Next.js app deployed on Vercel. A server-side route handles PDF analysis and any configured model request; the browser renders the original PDF, shows source highlights, holds the active review, and creates the DOCX.

There is no separate API service, worker, database, durable job queue, or Docker stack in the deployed Vercel MVP. Model requests use a bounded in-process concurrency gate; it does not provide a cross-instance quota on serverless deployments. After you choose **Save on this device**, the review screen keeps one tender draft in the browser's IndexedDB and autosaves later tender-review edits. It can resume only in the same browser profile; this is not cloud project history or encrypted storage. Browser cleanup and storage pressure can remove it. OEM uploads and assessment results remain session-only. Export important work. Use a non-confidential sample document.

## Limits

- Model-assisted extraction is a human-review draft, not an exhaustive completeness guarantee.
- Successful reviews show a page coverage ledger with routed pages, detected table rows where geometry is available, source matches, rejected suggestions and audit state. Detected source-table rows include candidate and accepted-match counts with a row highlight for inspection; unmapped rows may be headings or other content rather than omitted requirements. A page audit that reports no gaps is not a completeness guarantee; paths without that audit are marked not run.
- Structured table grouping currently requires selectable text, vector cell rectangles, a technical section heading, and the `Parameter` / `Required Specification` headers. Other table layouts use the configured GPT-6 Luna model path.
- The local app can OCR pages with little or no selectable text when Tesseract 5 and the configured trained-data languages are installed. Poppler is used for page rasterization when available; otherwise PDF.js renders the page. OCR is bounded by a per-page timeout and a document OCR time budget; pages left unprocessed are shown in the coverage ledger. OCR confidence and page boxes are approximate, and OCR-derived requirements must be checked visually. The hosted Vercel preview has no Tesseract or Poppler runtime and does not support scanned PDFs.
- Review each candidate and check the original tender for omissions before using the exported sheet.
- Refreshing or closing the browser clears the current review. Download the DOCX before leaving the page.
- The hosted preview accepts PDFs up to 4 MB, 120 pages, and 140,000 characters of selectable text per run.

## Links

- [Live MVP](https://tender-compliance-engine.vercel.app/)
- [Portfolio](https://devayushrout.me/)
- [How the evidence match works](https://tender-compliance-engine.vercel.app/method)

## Reliability checks

```sh
make web-test
make web-typecheck
make web-build
make web-test-pipeline
```

The pipeline check starts an isolated production Next.js server and a scripted model endpoint. It exercises real synthetic PDF uploads, routing, mixed table/prose extraction, source verification, omission recovery, and response-sheet edits without external model credentials. It is a deterministic contract test, not a measurement of live model accuracy. The regression suite also checks Unicode PDF export so comparison signs and units survive the generated PDF. CI runs all four checks on Node.js 22.

See [the reliability audit](docs/document-reliability-audit.md) for the client-tender acceptance case, implementation evidence, and remaining limits. The public demo is a separate deployment and must be reverified after release.
