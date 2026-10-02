# Tender Compliance Engine

Evidence-first technical tender compliance software for engineering, procurement, and technical sales teams.

> **Status:** CP00–CP61 are implemented. The backend now covers tender ingestion through evidence-backed compliance, final exports, and submission approval/versioning. The main remaining product work is post-build simplification, browser wiring for the completed Phase 2 review/submission APIs, and stronger end-to-end/adversarial verification.

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

### Phase 1 boundary

Phase 1 remains the tender-only workflow above. It does not itself claim vendor/OEM compliance.

## Implemented Phase 2

The repository now also implements OEM/vendor document ingestion, source-preserving evidence retrieval and curation, vendor specification extraction, deterministic unit/numerical comparison, evidence-backed qualitative reasoning, conflict detection, missing-evidence clarifications and deviations, human compliance review/audit, final matrix projection, XLSX/DOCX/PDF outputs, and versioned submission approval/locking.

The backend APIs and tests for these capabilities are implemented. The post-CP61 hardening plan intentionally treats **browser completion and true end-to-end usability** as separate work: some later Phase 2 APIs are not yet exposed completely through the web UI.

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

The implemented architecture uses:

- **Backend:** Python + FastAPI
- **Frontend:** React + Next.js + TypeScript
- **Database:** PostgreSQL
- **Object storage:** S3-compatible storage (MinIO locally)
- **Async infrastructure:** Redis-backed queue + worker for document processing
- **Document processing:** parser/OCR adapters behind interfaces
- **LLM use:** structured requirement extraction and language interpretation only where appropriate
- **Export:** Phase 1 XLSX plus final XLSX/DOCX/PDF submission outputs

The post-CP61 hardening goal is to keep this complete implementation understandable: simplify boundaries, remove dead ceremony, and prove the user journey end to end.

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

## Current product/API surface

The API now includes health, projects, tender/OEM uploads, processing/retry, requirements and source viewing, evidence, vendor specifications, compliance assessments, qualitative reasoning, conflicts, clarifications/deviations, final matrix/exports, and submission lifecycle endpoints.

The web app already supports the core project/tender requirement-review experience, but the final Phase 2 human-review/submission surfaces still need to be wired completely. See `docs/POST61_HARDENING_PLAN.md` for the focused post-build work.

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
- [Post-CP61 hardening plan](docs/POST61_HARDENING_PLAN.md)

- [Phase 1 PRD](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [Roadmap](docs/ROADMAP.md)
- [Evaluation strategy](docs/EVALUATION.md)
- [Security model](docs/SECURITY.md)

## License

No open-source license has been selected. Treat this repository as proprietary unless a license is added explicitly.
