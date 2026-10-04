<p align="center">
  <img src="apps/web/public/tce-mark.svg" width="88" alt="Tender Compliance Engine logo" />
</p>

<h1 align="center">Tender Compliance Engine</h1>

<p align="center">
  <strong>Turn technical tender documents and OEM evidence into a source-linked, reviewable compliance sheet.</strong>
</p>

<p align="center">
  <a href="https://github.com/ayushcodes13/tender-compliance-engine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ayushcodes13/tender-compliance-engine/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-15-black?logo=nextdotjs">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-16%2B-4169E1?logo=postgresql&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/license-proprietary-001742">
</p>

---

## What the product does

Tender Compliance Engine is built for engineering, procurement, technical sales, and bid teams that need to answer one practical question:

> **Given a tender requirement and the OEM/vendor documentation we have, what can we safely claim in the compliance sheet — and where is the evidence?**

The product keeps the workflow simple for the user while preserving the source trail underneath:

```text
Tender document
    ↓
Extract technical requirements
    ↓
Human review + source verification
    ↓
OEM / vendor source documents
    ↓
Evidence retrieval + vendor facts
    ↓
Deterministic numeric / unit comparison
    ↓
Evidence-backed compliance review
    ↓
Final compliance matrix
    ↓
XLSX / DOCX / PDF submission
```

No agent framework is required for this workflow. No vector database is required for the current product. The system deliberately keeps deterministic logic in code and uses an LLM only where language interpretation is useful.

## End-to-end user journey

| Step | User action | Product output |
| --- | --- | --- |
| 1 | Create a tender project | Persisted project workspace |
| 2 | Upload the tender | Immutable source version + processing status |
| 3 | Review extracted requirements | Source-linked technical requirements |
| 4 | Correct/split/merge/reorder requirements | Auditable reviewed requirement set |
| 5 | Upload OEM/vendor material or an existing vendor compliance sheet | Searchable source-preserving OEM evidence |
| 6 | Review proposed evidence | Accepted/rejected evidence per requirement |
| 7 | Run comparison | Deterministic numeric/unit result + bounded qualitative assessment |
| 8 | Resolve conflicts/gaps | Conflict, clarification, deviation, or review state |
| 9 | Confirm compliance decision | Human-reviewed assessment |
| 10 | Export | Final compliance matrix in XLSX, DOCX, or PDF |
| 11 | Lock/approve | Immutable submission version |

## What is supported today

### Inputs

| Input | Status | Notes |
| --- | --- | --- |
| Tender PDF | ✅ Supported | Digital and scanned/mixed PDFs; OCR is applied when required |
| OEM/vendor PDF | ✅ Supported | Datasheets, manuals, brochures, test reports, certificates, proposals, quotations, and existing vendor compliance sheets |
| Tender DOCX | ✅ Supported | Paragraphs and tables are preserved in source order; page numbers are not fabricated because DOCX has no stable physical pagination |
| OEM/vendor DOCX | ✅ Supported | Uses the same immutable source and evidence pipeline as OEM/vendor PDFs, including existing vendor compliance sheets |
| Images / PPT / arbitrary office files | — Not supported | Convert to PDF before upload for now |

### Outputs

- final compliance matrix in the browser;
- XLSX;
- DOCX;
- PDF;
- immutable submission versions with lock/approve/revoke lifecycle.

## Trust model

The product is intentionally conservative.

- **Missing evidence is not non-compliance.**
- **Same number is not the same technical claim.**
- Accuracy, resolution, precision, repeatability, sensitivity, range, entity, model, scope, and operating conditions remain distinct.
- Numerical thresholds and unit conversion are deterministic.
- OCR ambiguity remains visible.
- Every normal requirement and accepted evidence item is tied back to an immutable source version.
- Human review can confirm, override, reopen, comment, and resolve conflicts without erasing the original system output.

The highest-severity failure is **false compliance**: saying a product complies when the evidence does not establish it.

## Product architecture

```text
Next.js web app
      │
      ▼
FastAPI API
      │
      ├── PostgreSQL      projects / requirements / evidence / audit / submissions
      ├── S3 / MinIO      original documents / rendered pages / exports
      ├── Redis worker    document processing jobs
      ├── Tesseract       OCR
      └── OpenAI adapter  structured language extraction / bounded reasoning
```

The core runtime is one web app, one API, one worker, PostgreSQL, Redis, and S3-compatible object storage. It is not a microservice mesh.

## Repository structure

```text
.
├── apps/
│   ├── api/              FastAPI API + background worker
│   └── web/              Next.js product UI
├── docs/                 architecture, evaluation, security, runbooks
├── infra/                local infrastructure
├── docker-compose.yml    complete local stack
├── checkpoint.md         completed canonical build plan
├── AGENTS.md             engineering rules
└── README.md
```

## Local development

### Prerequisites

- Docker / Docker Compose
- Python 3.12+ for direct backend development
- Node.js 20+ for direct frontend development

### Infrastructure

```bash
make infra-up
make api-install
make api-migrate
make web-install
```

Run the API:

```bash
make api-dev
```

Run the frontend:

```bash
make web-dev
```

Then open:

```text
http://localhost:3000
```

For the bundled private-beta deployment, the backend bootstraps one owner/workspace automatically. No manual membership seed is required. Development-header auth remains available for tests and direct local development.

## AI configuration

The bundled stack needs one external AI credential:

```bash
cp .env.example .env
# edit .env and set:
OPENAI_API_KEY=...
docker compose up --build
```

Migrations run before the API starts, the object-storage bucket is created on API startup, and the same OpenAI configuration is supplied to the processing worker. Then open `http://localhost:3000`.

This **single-workspace mode is designed for private pilots and one-customer deployments**. It is not a substitute for a real identity provider when the product is exposed as a public multi-user SaaS.

## Quality gates

CI checks the parts that matter most for this product:

- Python linting;
- backend unit/integration/acceptance tests;
- extraction/citation evaluation gates;
- zero-false-compliance adversarial gates;
- cross-tenant security tests;
- frontend TypeScript and production build;
- API, worker, and web Docker builds;
- unsafe raw-HTML rendering guard.

The final manual product-owner acceptance checklist is in [docs/POST61_RELEASE_REVIEW.md](docs/POST61_RELEASE_REVIEW.md).

## Current status

**CP00–CP61 are complete.** Post-build hardening PRs have also completed the browser compliance-review flow, final matrix/export/submission UI, real OEM upload → worker integration, and adversarial security review.

The remaining focus is deliberately commercial and practical:

1. make the UI feel like a finished product;
2. run representative real tender + OEM documents through the deployed product;
3. fix only the issues those real runs expose.

We are **not** adding agent orchestration, a vector database, or a new RAG platform unless real customer usage proves one is necessary.

## Reference implementations studied

Production patterns were reviewed from:

- `Bynd-ai/chat@prod-trunk` — document upload UX, error boundaries, request correlation, deployment/environment discipline, sidebar/product navigation;
- `Bynd-ai/metric-search` — environment selection, PDF review UX, structured logging, failure visibility, job isolation, LLM usage/cost discipline.

These are references only. This repository does not copy private/unlicensed Bynd implementation code.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Product requirements](docs/PRD.md)
- [Data model](docs/DATA_MODEL.md)
- [Evaluation strategy](docs/EVALUATION.md)
- [Security model](docs/SECURITY.md)
- [Post-CP61 release review](docs/POST61_RELEASE_REVIEW.md)
- [Bynd reuse audit](docs/BYND-REUSE-AUDIT.md)

## License

No open-source license has been selected. Treat this repository as proprietary unless a license is added explicitly.
