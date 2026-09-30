# Tender Compliance Engine

Evidence-first technical tender compliance software for engineering, procurement, and technical sales teams.

> **Status:** Phase 1 foundation. The current scope is tender ingestion, requirement extraction, normalization, traceable citations, human review, compliance-matrix generation, and export preparation. Vendor/OEM compliance assessment belongs to Phase 2.

## Why this exists

Technical tender responses are still assembled through a slow manual loop: read large PDFs, find specifications, clean OCR errors, split requirements, build a compliance matrix, trace each row back to the source, and repeatedly verify that nothing was invented or lost.

Tender Compliance Engine is designed to turn that process into a structured, auditable workflow without treating an LLM as the source of truth.

## Product principles

1. **Evidence over hallucination.** Every extracted requirement must remain traceable to its source document and location.
2. **Missing evidence is not non-compliance.** Absence and contradiction are different states.
3. **Human review is a first-class workflow.** Uncertain OCR, ambiguous requirements, and later compliance decisions must be reviewable.
4. **Deterministic logic owns math.** Numerical thresholds, units, ranges, and tolerances should be evaluated in code rather than delegated to an LLM.
5. **No fabricated citations.** Page, clause, text span, and bounding-box metadata are recorded only when actually known.
6. **Version everything that matters.** Documents, requirements, review decisions, and later evidence must be auditable.
7. **Build the boring pipeline first.** Phase 1 intentionally avoids premature agents/RAG complexity.

## Phase 1

```text
Tender document(s)
        │
        ▼
 PDF/DOCX parsing + OCR
        │
        ▼
Source-preserving page representation
        │
        ▼
Technical requirement extraction
        │
        ▼
Requirement normalization
        │
        ▼
Human review / edit / split / merge
        │
        ▼
Compliance matrix
        │
        ▼
Excel export
```

### Phase 1 capabilities

- Create a tender project.
- Upload one or more tender documents.
- Parse digitally generated PDFs and route scanned pages through OCR.
- Extract explicit technical requirements without inventing missing text.
- Preserve document, document version, page, clause/section, source text, and coordinates when available.
- Normalize technical constraints without changing meaning.
- Review, edit, split, merge, reorder, categorize, and annotate requirements.
- Audit manual changes.
- Generate a structured compliance matrix.
- Export reviewed requirements to Excel.

### Explicitly out of scope for Phase 1

- Vendor/OEM compliance claims.
- Semantic retrieval over OEM documents.
- Requirement-to-OEM evidence matching.
- Automated compliant/non-compliant decisions.
- Contradiction detection across OEM documents.
- OEM clarification generation.

Those are designed into the architecture as future interfaces, not implemented prematurely.

## Planned Phase 2

Phase 2 adds OEM/vendor document ingestion, source-preserving evidence retrieval, deterministic numerical comparison, evidence-backed compliance reasoning, contradiction detection, missing-information detection, clarification questions, and final submission-ready exports.

The eventual assessment states are:

- `COMPLIANT`
- `NON_COMPLIANT`
- `PARTIAL`
- `NOT_DEMONSTRATED`
- `CONFLICT`
- `HUMAN_REVIEW_REQUIRED`

## Repository structure

```text
.
├── apps/
│   ├── api/                  # FastAPI backend skeleton
│   └── web/                  # Next.js frontend skeleton
├── docs/
│   ├── ARCHITECTURE.md       # System boundaries and data flow
│   ├── DATA_MODEL.md         # Phase 1 schema + Phase 2-compatible extensions
│   ├── EVALUATION.md         # Accuracy and safety evaluation strategy
│   ├── PRD.md                # Phase 1 product requirements
│   ├── ROADMAP.md            # Delivery milestones
│   └── SECURITY.md           # Threat model and controls
├── infra/
│   └── docker-compose.yml    # Local Postgres, Redis, and MinIO
├── .github/
│   ├── workflows/ci.yml
│   └── pull_request_template.md
├── .env.example
├── .gitignore
├── AGENTS.md                 # Canonical AI/coding instructions
├── CLAUDE.md -> AGENTS.md    # Same project instructions for Claude-compatible workflows
└── Makefile
```

## Tech direction

The starter architecture uses:

- **Backend:** Python + FastAPI
- **Frontend:** React + Next.js + TypeScript
- **Database:** PostgreSQL
- **Object storage:** S3-compatible storage (MinIO locally)
- **Async infrastructure:** Redis-backed queue interface (worker integration is a later milestone)
- **Document processing:** parser/OCR adapters behind interfaces
- **LLM use:** structured requirement extraction and language interpretation only where appropriate
- **Export:** Excel first; DOCX/PDF later

The goal is to keep the MVP simple while leaving clean seams for Phase 2.

## Local development

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker + Docker Compose

### 1. Configure environment

```bash
cp .env.example .env
```

### 2. Start infrastructure

```bash
make infra-up
```

### 3. Run the API

```bash
make api-install
make api-dev
```

The health endpoint is available at:

```text
GET http://localhost:8000/health
```

### 4. Run the web app

```bash
make web-install
make web-dev
```

Open `http://localhost:3000`.

## Current API surface

The initial API intentionally contains only the foundation needed to verify the app boots correctly:

```text
GET /health
```

Project creation, upload, document-processing, requirement, citation, review, and export endpoints are planned milestone-by-milestone in `docs/ROADMAP.md`.

## Definition of trustworthy behavior

The most important failure class is **false compliance**: claiming that a product meets a tender requirement when the evidence does not establish that conclusion. As Phase 2 lands, evaluation and release gates should be biased toward conservative outcomes rather than impressive-looking guesses.

For Phase 1, the analogous safety bar is **false extraction/citation**: a requirement or source location must not be created unless it is supported by the tender document.

## Development rules

### Pull-request workflow

All substantive changes use a branch and pull request. Do not push feature, fix, documentation, configuration, or refactor work directly to `main`.

Each PR should be one coherent review unit, explain **why** it exists, describe **what changed**, identify scope and provenance/data impact, list verification performed, and state known risks or limitations. Required CI should pass before merge; squash merge is the default.

Before implementing a milestone:

1. State the milestone and scope.
2. Identify dependencies and files to change.
3. Keep the change minimal.
4. Add or update tests.
5. Preserve auditability and source traceability.
6. Do not silently rewrite working components.

See `AGENTS.md` for the full project instructions.

## Canonical execution plan

Work should follow [Canonical checkpoint plan](checkpoint.md) from the first unchecked checkpoint. Completed checkpoints are crossed out there, and the plan is updated through PRs whenever product requirements or architecture change.

## Documentation

- [Canonical checkpoint plan](checkpoint.md)
- [Bynd reuse audit](docs/BYND-REUSE-AUDIT.md)

- [Phase 1 PRD](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [Roadmap](docs/ROADMAP.md)
- [Evaluation strategy](docs/EVALUATION.md)
- [Security model](docs/SECURITY.md)

## License

No open-source license has been selected. Treat this repository as proprietary unless a license is added explicitly.
