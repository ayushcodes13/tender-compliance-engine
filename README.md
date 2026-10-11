<p align="center">
  <img src="apps/web/public/tce-mark.svg" width="76" alt="Tender Compliance Engine logo" />
</p>

<h1 align="center">Tender Compliance Engine</h1>

<p align="center">
  <strong>Turn a technical tender into a source-linked specification sheet for the OEM to complete.</strong>
</p>

<p align="center">
  <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-15-black?logo=nextdotjs">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-16%2B-4169E1?logo=postgresql&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/license-proprietary-001742">
</p>

![Tender Compliance Engine landing page](docs/screenshots/screenshot-landing.png)

---

## See the workflow

The screenshots below use synthetic test data. They show the current interface and do not represent a completed client tender or a supplier compliance decision.

![Tender workspace with project status and review progress](docs/screenshots/screenshot-dashboard.png)

### 1. Upload and organize the tender

The project workspace keeps the immutable tender version, processing state, and next review action visible.

![Tender project workspace with source documents and workflow steps](docs/screenshots/project-workspace.png)

### 2. Review requirements against the cited source

Reviewers can inspect extracted requirements alongside the rendered tender page. Source wording and location remain visible so uncertain extraction can be checked against the document.

![Requirement review with tender source and highlighted citation](docs/screenshots/source-linked-review.png)

### 3. Export the OEM response sheet

The response sheet contains the tender's original technical wording and blank OEM response fields. Source links and validation details remain available in the app for review.

![Tender-derived technical response sheet with a visible no-extraction warning and page links](docs/screenshots/oem-response-sheet.png)

## Product scope

The client-facing product flow is:

```text
Tender upload
  → parsing and OCR
  → source-linked requirement extraction
  → human review and correction
  → post-export wording and source validation
  → blank OEM response sheet
```

The generated response sheet contains only the technical specifications in the tender's selected technical-specification section or clearly identifiable specification tables. It preserves source wording, numbering, nested rows, and blank OEM response cells. The system does not add recommendations, interpretations, or compliance decisions. OCR uncertainty, failed source checks, possible omissions, and technical windows with no extracted rows stay visible for human review. A passing check confirms generated rows and citations; it does not prove that every tender specification was found.

Supported tender inputs include PDF and DOCX. The primary OEM response sheet is a DOCX. Additional matrix formats and OEM evidence/compliance services remain in the backend but are not part of the client-facing workflow. See [the architecture guide](docs/ARCHITECTURE.md) for system boundaries and [the checkpoint plan](docs/checkpoint.md) for implementation status.

## Current readiness

**The product workflow is implemented, but the example set and client acceptance are not signed off.** Checkpoint 70 remains in progress. Its open work includes human classification of sample findings, tender-wide completeness decisions, and a full acceptance run in the intended client environment. See [Checkpoint 70](docs/checkpoint.md#L3533) and the [current client-readiness checklist](docs/CLIENT_READINESS.md).

Known sample-review work includes exact-wording differences, possible omitted requirements, blank response-sheet decisions, and unresolved coverage findings. These require review against the original pages and the supplied response sheets. The app must not infer a supplier decision from an empty cell or treat an unconfirmed possible omission as a fact.

The private pilot has no user sign-in and is intended for local or trusted private-network use. Do not expose it directly to the public internet. Production use still needs client-specific identity, storage, malware-scanning, backup, and service-health configuration.

GitHub Actions verification is temporarily unavailable because the repository account has a billing/spending restriction. This README does not treat blocked jobs as passing checks. Restore billing and rerun the required workflows before release sign-off.

## Start a private pilot

Prerequisites: Docker with Compose support, and an OpenAI-compatible API credential configured for the selected model endpoint.

```bash
cp .env.example .env
# Add the required AI endpoint/key/model settings to .env
make pilot-start
```

The startup command validates configuration, starts the database, queue, scanner, API, processing worker, and web app, and waits for the readiness endpoint. Open [http://localhost:3000](http://localhost:3000). Keep `.env` private; never commit credentials.

For direct local development, see the Makefile targets and [the development notes](docs/ARCHITECTURE.md). The bundled pilot creates one workspace and is not a multi-tenant SaaS deployment.

## How source and review states work

- A requirement keeps its tender source wording, document version, page or clause when known, and approximate/exact location status.
- Reviewers can edit, split, merge, reorder, confirm, or flag extracted requirements while retaining the audit trail.
- OCR ambiguities and unverified coverage findings require human review.
- Export validation reads the generated DOCX, checks the technical wording and source quotations, and blocks files when checks fail or need review.
- A passing row check is not a guarantee of tender-wide completeness; unresolved coverage findings and zero-row windows remain visible.

## Architecture

```text
Next.js web app
      │
      ▼
FastAPI API ─── PostgreSQL
      │
      ├── shared pilot volume for originals, page renders, and exports
      ├── Redis-backed processing worker
      ├── ClamAV upload scanning
      ├── Tesseract OCR
      └── OpenAI-compatible structured technical-specification extraction
```

The pilot is a compact application stack, not a microservice mesh. OEM-evidence, assessment, and submission modules are retained in the backend for now, but the current client workflow does not expose them. Storage and provider integrations sit behind adapters so a later deployment can use managed services without changing the product's source-traceability rules.

## Repository map

```text
apps/api/              API, application services, persistence, and worker
apps/web/              Project, upload, review, source viewer, matrix, and export UX
docs/                  Architecture, security, evaluation, release review, and checkpoint plan
infra/                 Local infrastructure configuration
docker-compose.yml      Bundled private-pilot stack
AGENTS.md               Contribution and product guardrails
```

## Development checks

The repository's GitHub Actions workflows run backend checks, extraction/citation and security gates, frontend type-check/build, container builds, and bundled-stack smoke checks. Run the focused checks for the area you change; the required GitHub workflows must also pass before normal release sign-off.

Current local verification for this branch will be recorded in its pull request. CI remains pending until the billing restriction is resolved.

## Design and product principles

- Never invent a technical requirement, citation, page, source quote, or supplier status.
- Preserve source wording and distinguish exact from approximate locations.
- Keep OCR uncertainty visible instead of silently correcting it.
- Prefer conservative human review over unsupported certainty.
- Treat uploaded files as untrusted input and document text as data, never as application instructions.

See [the design notes](apps/web/DESIGN.md), [security guidance](docs/SECURITY.md), and [the canonical checkpoint plan](docs/checkpoint.md).
