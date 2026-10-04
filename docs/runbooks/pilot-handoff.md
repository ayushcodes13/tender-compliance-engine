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
cp .env.example .env
```

Put the real key in `.env`:

```text
OPENAI_API_KEY=...
```

Start everything:

```bash
docker compose up --build
```

Open:

```text
http://localhost:3000
```

## What the customer does

1. Create a tender project.
2. Upload the tender PDF or DOCX.
3. Let the worker parse/OCR/extract source-linked requirements.
4. Review/correct the extracted requirements.
5. Upload vendor/OEM material:
   - datasheets;
   - manuals;
   - brochures;
   - certificates;
   - test reports;
   - quotations;
   - proposals;
   - an existing vendor compliance sheet.
6. Review the evidence proposed for each requirement.
7. Review the deterministic numeric/unit comparison and bounded qualitative
   assessment.
8. Resolve conflicts, missing evidence, clarifications, and deviations.
9. Confirm or override the final compliance decision.
10. Open the final compliance sheet.
11. Export XLSX, DOCX, or PDF.
12. Lock/approve a submission version when ready.

## Vendor/OEM scope

The product is vendor-agnostic: no OEM name or product family is hard-coded into
the workflow.

That does **not** mean every arbitrary file will automatically produce a
confident COMPLIANT/NON_COMPLIANT result.

The safe contract is:

- PDF/DOCX technical material is accepted;
- explicit tender requirements are extracted and source-linked;
- vendor evidence is searched/reviewed;
- supported numerical comparisons are deterministic;
- when evidence is missing, ambiguous, contradictory, or refers to the wrong
  metric/model/scope, the row remains unresolved
  (`NOT_DEMONSTRATED`, `CONFLICT`, or `HUMAN_REVIEW_REQUIRED`) rather than
  guessing;
- the final compliance sheet/export is still available and preserves those
  unresolved states for the reviewer.

This conservative behavior is part of the product, not an error condition.

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
docker compose down
```

Start again:

```bash
docker compose up
```

Do **not** use `docker compose down -v` on a customer pilot unless you intend
to delete the PostgreSQL, Redis, and document-storage Docker volumes.

## Before the first paying pilot

Run the manual acceptance checklist in
[../POST61_RELEASE_REVIEW.md](../POST61_RELEASE_REVIEW.md) using:

- one representative real tender;
- one scanned/mixed-quality tender;
- representative vendor/OEM technical documentation;
- the false-compliance adversarial cases in that checklist.

After that, product work should be driven by failures observed in real tenders,
not by adding generic agent/RAG infrastructure.
