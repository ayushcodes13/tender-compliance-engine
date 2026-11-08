# Private operator pilot (no new cloud hosting)

This runbook uses an existing customer-controlled machine or private VM. It avoids a new hosting charge, but model inference may incur provider costs. Do not use confidential tenders until the customer approves the configured model endpoint and retention/data handling.

## Requirements

- Node.js 22.13+ and npm.
- A machine with memory headroom; 32 MiB upload acceptance is a software ceiling, not a proven safe capacity target. Until measured, use smaller documents and one operator at a time.
- Approved `OPENAI_API_KEY` and, if applicable, `OPENAI_BASE_URL` / `OPENAI_MODEL=gpt-6-luna` in `apps/web/.env.local`.
- Optional local Poppler and Tesseract installations for scanned PDFs. Hosted OCR is unavailable.

## Start and stop

```sh
cp .env.example apps/web/.env.local
# Edit apps/web/.env.local with the approved model endpoint and a strong APP_ACCESS_PASSWORD.
make web-install
make pilot-start
```

Open `http://127.0.0.1:3307` from the same machine. Keep the service on loopback. For remote access, use the customer's existing VPN or an approved TLS reverse proxy with access controls; do not expose the development port directly to the internet. Process one document at a time until memory and concurrency testing has been completed on the target machine.

After analysis, inspect every cited page, correct/remove rows, and export the reviewed response sheet. Refreshing the browser loses the review. Stop the service when the session ends:

```sh
make pilot-stop
```

## Offline verification without model calls

```sh
npm --prefix apps/web test
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
npm --prefix apps/web run test:pipeline
```

The pipeline uses synthetic PDFs and a scripted provider; it does not measure real-tender accuracy or hosted capacity. `npm --prefix apps/web run test:stress` targets a separate local API at port 3000 and makes model-backed requests; do not run it as an offline/no-cost check. For controlled stress work, first change the harness to accept an explicit URL, use an isolated server, and provide an approved bounded test endpoint.

## Upload boundaries

The API rejects multipart bodies over `MAX_FILE_BYTES + 256 KiB` before parsing them. Outside Vercel, `MAX_FILE_BYTES` defaults to 32 MiB; set a lower explicit value for constrained machines. Vercel remains limited by its platform 4.5 MB function body cap regardless of the application setting. The API also checks the PDF signature and a 120-page limit.
