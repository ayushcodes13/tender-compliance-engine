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
| 5 | Upload OEM/vendor material | Searchable source-preserving OEM documents |
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
| OEM/vendor PDF | ✅ Supported | Datasheets, manuals, brochures, test reports, certificates, proposals, quotations |
| DOCX parsing | 🟡 Implemented behind the parser | The parser/worker support DOCX, but the current upload validation gate still accepts PDF only. This is tracked as production-wiring work and should not be advertised to customers until the upload path is enabled end to end. |
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

The current development identity flow uses development headers and requires a local membership seed. The production-readiness pass is simplifying this so a fresh self-hosted deployment can bootstrap a single workspace without manual database work.

## AI configuration

The runtime adapter reads:

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o
```

The API key is never committed. A production-wiring pass is in progress to make this configuration consistent across the root environment, API container, and worker container.

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

1. remove the last environment/bootstrap friction;
2. make the UI feel like a finished product;
3. run representative real tender + OEM documents through the deployed product;
4. fix only the issues those real runs expose.

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
