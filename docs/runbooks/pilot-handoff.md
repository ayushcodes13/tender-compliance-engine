# Private Pilot Handoff

This is the shortest path from the repository to a usable one-customer pilot.

## What you need

- Docker with Docker Compose.
- An OpenAI API key.

You do **not** need to create PostgreSQL, Redis, object-storage credentials,
database users, migration tables, or a login account manually for this mode.

## Start the product

```bash
git clone https://github.com/ayushcodes13/tender-compliance-engine.git
cd tender-compliance-engine
OPENAI_API_KEY=sk-... make pilot-start
```

That is the complete bundled-pilot handoff. The command checks Docker and
Compose, validates the one required external secret, starts every service,
waits for the browser-facing readiness endpoint, and prints the URL.

If you prefer not to pass the key through the shell environment, copy
`.env.example` to `.env`, set `OPENAI_API_KEY`, and run
`make pilot-start`.

Open:

```text
http://localhost:3000
```

The web UI and API are bound to `127.0.0.1` by default. Since this pilot has
no user sign-in, keep it local or provide remote access through a trusted
private reverse proxy or VPN. Do not expose the UI directly to the internet.

## What the customer does

1. Create a tender project.
2. Upload the tender PDF or DOCX.
3. Let the worker parse/OCR the tender and extract technical specifications.
4. Review the numbered items, nested rows, source wording, and cited tender pages.
5. Resolve extraction warnings and surfaced coverage findings, or leave them
   clearly marked for human review.
6. Export the source-linked DOCX response sheet with blank OEM response fields.
7. Send that response sheet to the OEM to complete.

## Vendor/OEM scope

This pilot prepares the OEM response sheet from the tender alone. It does not
ingest OEM evidence, fill in supplier responses, or decide whether a product
complies. OEM answers are entered by the supplier after the sheet is exported.

## Readiness check

```bash
curl -fsS http://localhost:3000/api/backend/ready
```

Expected top-level status:

```json
{"status": "ready"}
```

The endpoint also reports dependency-level readiness.

Production processes also validate configuration **before** serving traffic.
Outside the bundled Compose stack, production will refuse to start rather than
silently substituting in-memory adapters when any of these are missing:

- PostgreSQL (`DATABASE_URL`);
- Redis (`REDIS_URL`);
- durable local or S3-compatible object storage;
- `OPENAI_API_KEY`;
- the currently supported private-pilot `AUTH_MODE=single_workspace`.

The bundled Compose file supplies everything except the OpenAI key.

## Stop/restart

Stop while keeping data:

```bash
make pilot-stop
```

Start again:

```bash
make pilot-start
```

Check status at any time:

```bash
make pilot-status
```

Do **not** use `docker compose down -v` on a customer pilot unless you intend
to delete the PostgreSQL, Redis, and document-storage Docker volumes.

## Before the first paying pilot

Complete the tender-only release gates in
[../CLIENT_READINESS.md](../CLIENT_READINESS.md). Use the supplied tender and
response-sheet examples, then repeat the upload-to-export flow on a
representative client tender in the private pilot environment. Do not present
an export as complete while its source-validation or coverage findings still
need review.
