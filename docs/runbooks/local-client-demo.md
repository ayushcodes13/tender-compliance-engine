# Local client demo

This runbook describes the verified Phase 1 demo path using the Example 2
technical tender. It demonstrates extraction and review, not a production
deployment or a complete compliance assessment.

## Start an isolated demo stack

Use a disposable PostgreSQL database, a dedicated Redis database (for example
DB 15), and a local filesystem object-storage directory. Do not point this demo
at an existing project database or shared object-storage bucket. Configure the
API and web apps with matching single-workspace development identity values.
Keep provider credentials in an untracked local environment file.

From the repository root:

```sh
uv sync --project apps/api --extra dev
npm ci --prefix apps/web
```

Set the API environment to the isolated database and Redis DB, local storage,
and development single-workspace auth. Apply migrations and run the API,
worker, and web app in separate terminals:

```sh
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api uvicorn tender_compliance_api.main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
uv run --project apps/api python -m tender_compliance_api.worker
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3307
```

Set `NEXT_PUBLIC_API_URL=/api/backend` and
`BACKEND_INTERNAL_URL=http://127.0.0.1:8000` for the web app. Confirm
`http://127.0.0.1:8000/ready` reports the database, queue, worker, storage, and
malware scanner ready before uploading.

## Demo flow

1. Create a new project and upload the provided Example 2 technical tender PDF.
2. Wait for processing to complete, then open the Review view.
3. Select a numbered requirement and confirm the displayed page and source
   highlight against the original PDF. Keep requirements in `UNREVIEWED` unless
   a reviewer has actually reviewed them.
4. Open the Matrix view and download the blank vendor response DOCX.
5. Inspect the DOCX in Word or LibreOffice, including later pages and repeated
   table headers. Response cells are intentionally blank; this is not an OEM
   compliance assessment.

## Verified example and limits

On 2026-10-17, a fresh project was processed from the 37-page Example 2 PDF.
The run produced 116 requirements, all still unreviewed. The source viewer's
page-8 exact quote and highlight aligned for sampled rows. The exported DOCX
contained 119 specification rows and blank compliance/deviation cells; its 18
rendered pages were inspected for clipping and table layout. A 390×844 review
viewport kept the source and requirement details readable.

This sample exposed symbol fidelity limits: superscript exponents in the source
PDF appear flattened in extracted/exported text, and a degree symbol in one
sampled row appeared as a letter `o`. Preserve these rows for human review;
do not treat this run as proof of numeric fidelity or OCR accuracy. The sample
PDF already has a text layer, so scanned-document OCR was not exercised. The
demo did not establish extraction completeness, production security or
reliability, multi-user isolation, or Phase 2 vendor compliance. Two provider
requests returned HTTP 400 before the extraction completed after fallback; the
run demonstrates this configuration's successful path, not general provider
reliability. Optional verifier passes were disabled for this run.

The environment used for verification was local and isolated. Recreate the
database, Redis namespace, and storage directory for each fresh demo run; never
delete or reuse another user's development data as cleanup.
