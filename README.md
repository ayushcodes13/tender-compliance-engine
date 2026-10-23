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

When a technical page contains a selectable two-column table headed **Parameter** and **Required Specification**, the app uses PDF cell geometry to keep each parameter with its full specification cell. It also preserves blank specification rows and a following **Other requirements** bullet list. The DOCX uses the four-column response layout shown in the reference, with compliance and remarks left blank. Other document layouts use GPT-6 Luna to route and extract candidate requirements for human review.

The app does not decide whether a supplier complies. Every candidate starts in **Needs review** and should be checked against the original tender.

## Screenshots

The screenshots below are real captures from the hosted MVP. The review example uses a sample PDF and shows the currently deployed **rule-based preview**. Its candidate list can include false positives and can miss requirements; the count is not a completeness measure, and the example rows have not been approved by a reviewer.

<p align="center">
  <img src="docs/screenshots/readme-review-evidence.jpg" alt="Review workspace with a source-matched candidate, cited tender page, and bounding-box highlight" width="100%" />
</p>

The yellow page highlight is positioned from the matched source text. Selecting a candidate opens its citation and quote; the reviewer can compare both with the original page before marking it checked.

## Try the hosted demo

Open [Tender Review on Vercel](https://tender-compliance-engine.vercel.app/). Upload a readable, text-based PDF (up to 4 MB and 120 pages), choose a candidate, inspect its citation and page highlight, and download the response sheet.

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

Prerequisites: Node.js 20+, npm, and GPT-6 Luna credentials configured in the local environment. For local scanned-page OCR, install Tesseract 5 with the configured language data; OCR is optional for text-based PDFs.

```sh
git clone https://github.com/ayushcodes13/tender-compliance-engine.git
cd tender-compliance-engine
cp .env.example .env.local
make web-install
make pilot-start
```

The app uses GPT-6 Luna for model-assisted extraction. Set `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL=gpt-6-luna` in `apps/web/.env.local`. Tender text and page images are sent to the configured endpoint for processing. There is no Ollama or open-source model fallback. Structured source tables with explicit cell geometry may be grouped directly from the PDF without an LLM call.
For a local macOS setup, install Tesseract 5 and Poppler's `pdftoppm` tools with `brew install tesseract poppler`. Tesseract and its trained data use Apache-2.0; Poppler is an optional external renderer under GPL terms and is not bundled by this project. The app detects standard Homebrew paths and `PATH`; set `TESSERACT_BINARY` or `PDFTOPPM_BINARY` in `.env.local` if either executable is installed elsewhere. `TESSERACT_LANG` defaults to `eng`; set it to a `+`-separated language list such as `eng+hin` only after installing each matching trained-data file. OCR text stays separate from native PDF text, carries approximate page boxes and Tesseract confidence, and every OCR-derived requirement remains marked for human verification. The hosted Vercel preview does not bundle these local binaries and reports scanned documents as unsupported there.
Open [http://127.0.0.1:3307](http://127.0.0.1:3307). Stop the local app with:

```sh
make pilot-stop
```

## Architecture

The hosted MVP is one Next.js app deployed on Vercel. A server-side route handles PDF analysis and any configured model request; the browser renders the original PDF, shows source highlights, holds the active review, and creates the DOCX.

There is no separate API service, worker, database, job queue, or Docker stack in the deployed MVP. Uploaded files and review results are not saved as a project history. The hosted site has no sign-in, so use a non-confidential sample document.

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
