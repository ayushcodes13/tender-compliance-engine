# Tender Review

A small single-user demo that turns a text-based tender PDF into a source-linked technical response sheet. A reviewer can open each citation, see the cited page and its bounding box, mark the quote checked, and download a DOCX with blank OEM response fields.

## Run locally

Prerequisites: Node.js 20+, npm, and an OpenAI-compatible chat-completions credential.

```bash
cp .env.example .env.local
# Set OPENAI_API_KEY. Set OPENAI_BASE_URL and OPENAI_MODEL if using Azure.
make web-install
make pilot-start
```

Open [http://127.0.0.1:3307](http://127.0.0.1:3307). Stop the app with `make pilot-stop`.

## One-app architecture

```text
Next.js app (Vercel or localhost)
  ├── one synchronous server-side PDF analysis action
  ├── PDF.js reads source text and computes page-coordinate boxes
  ├── OpenAI-compatible model proposes literal, page-local quotes
  └── browser renders the original PDF and creates the DOCX
```

The deployed product is one Next.js app. It has no separate FastAPI service, job worker, database, queue, or Docker stack. Tender bytes and analysis results remain in the active browser session and are not saved by the app. The model key stays server-side.

## Evidence rules and limits

- A proposed requirement appears only if its quote can be matched to selectable text on the cited page and its geometry can be found.
- Every row starts as **Needs review**. A reviewer must inspect the source before marking it checked.
- The response sheet contains the matched source wording, citation page, and blank OEM response field. It does not make supplier decisions.
- The extraction is not a completeness guarantee. Review the original tender for omissions.
- Scanned PDFs and OCR are not supported. Use a text-based PDF.
- The hosted MVP accepts PDFs up to 4 MB, 120 pages, and 140,000 characters of selectable text per run. The single extraction call has a 48-second timeout.
- Refreshing or closing the browser clears the current review. Download the DOCX before leaving the page.

For Vercel, set the project root to `apps/web` and configure `OPENAI_API_KEY`, plus `OPENAI_BASE_URL` and `OPENAI_MODEL` for the selected provider. Do not put credentials in `NEXT_PUBLIC_*` variables. The requested hostname is `tender.devishot.me`; add it to the Vercel project after the deployment is ready, then point its Namecheap DNS record to the target Vercel supplies.

## Checks

```bash
make web-typecheck
make web-build
```
