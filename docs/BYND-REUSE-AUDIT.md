# Bynd Repository Reuse Audit

**Audit date:** 2026-10-01

## Purpose

This document records what the Tender Compliance Engine can learn from the accessible `Bynd-ai` GitHub organization and, equally importantly, what it should **not** inherit.

The goal is not to turn this project into a bundle of Bynd dependencies. The goal is to reuse proven engineering ideas—contracts, invariants, failure semantics, tests, UI behavior, operational patterns—while keeping this repository self-contained, evidence-first, and appropriate for technical tender compliance.

## Audit scope and method

Repository inventory: 108 accessible repositories were enumerated. Root structure was inspected across the full inventory. Repositories with material overlap in document ingestion/OCR/tables, provenance/citations, validation/evidence, auth/tenancy, queues/workers, evals, exports, UI review, and deployment were then read more deeply at README/docs/source level.

This is an architecture/reuse audit, **not** a claim that every line in every repository was code-reviewed. Low-overlap scraping, alerting, company-data, and report-generation repositories were still inventoried so they were not silently skipped; deeper inspection was focused where reuse could materially change this project's checkpoint plan.

## Reuse and licensing policy

- Bynd-internal/private repositories are references by default, not code sources. No private source, prompt, asset, secret, environment identifier, or customer data should be copied into this project.
- `Bynd-ai/table_grid` contains an MIT license. Code reuse could be considered later only when there is a concrete reason, with required copyright/license notice preserved. This audit copies no implementation code.
- `Bynd-ai/chat` README declares `AGPL-3.0-only`. Do not copy its implementation code into this proprietary repository without a deliberate licensing decision; its viewer behavior is used only as a design reference.
- `Bynd-ai/bynd-ui` identifies its package license as `UNLICENSED` and publishes to a restricted GitHub registry. Do not copy it or add it as a dependency without explicit permission/ownership/access planning.
- A repository having useful behavior does not override Tender Compliance's stricter rules. In particular, OCR ambiguity must remain reviewable and compliance must fail closed/abstain rather than guess.

## Highest-value reuse decisions

| Bynd reference | What is useful here | Mapped checkpoint(s) | Decision |
| --- | --- | --- | --- |
| `validation-service` | Typed verdicts/reason codes, fail-closed abstention, one-result-per-target, privacy-safe telemetry, provider error taxonomy, eval/benchmark gates | CP31, CP43–46, CP50, CP54–57 | **ADOPT patterns** |
| `validation-engine` | Content-addressed PDF/page extraction cache, strict page authority, conservative cross-page windows, layered evals and mutation/regression/stress datasets | CP24, CP27, CP30, CP43–44 | **ADOPT patterns** |
| `industry-report-agentic` | Pre-transform audit copies, async validation barrier, multi-lane merge/conflict behavior, citation/evidence UI mechanics | CP30, CP36, CP56 | **ADOPT patterns; frontend pattern already partly used** |
| `metric-search` | PDF text-layer trust gate for scans/hidden OCR/invisible text and document corruption; consumer job patterns | CP18–21 | **ADOPT trust-gate ideas** |
| `final-final-chunking-pipeline` | One document/message per isolated job, job IDs, per-stage timing tree, incremental derived artifacts | CP18, CP20, CP24, CP46–47 | **ADOPT architecture ideas when scale requires** |
| `finance-data-ingestion-service` | Bounded concurrency, retry budgets, schema-drift warnings, Sentry-style error reporting, immutable image deployment | CP18, CP46–47 | **ADOPT patterns** |
| `company-reports-backend` | Async SQLAlchemy session boundary, Alembic usage, organization/membership model, auth context/service layering | CP06–08 | **ADOPT patterns; implement fresh** |
| `universal-auth-service` | Request IDs, CSP/security headers, redirect allowlist, prod/dev origin separation, rate limiting | CP08, CP45 | **ADOPT security patterns** |
| `table_grid` | Docling benchmark candidate, exact-source verification UI, citation service decomposition, dense grid review | CP22–23, CP36 | **EVALUATE; MIT license verified** |
| `ocr-table-fixes-discovery` | Cell confidence/original text/bbox model and ambiguity diagnostics for OCR table numbers | CP23, CP33 | **ADOPT metadata/diagnostic pattern; reject silent fixing** |
| `engineering-docs` | LLM per-call/run cost logging and PR review discipline | CP26, CP46 | **ADOPT cost-meter requirements** |
| `bynd-devops-system` | Migrate-before-deploy, OIDC, GitHub environments, immutable tags, Container Apps vs Jobs split | CP07, CP47 | **ADOPT deployment principles** |
| `chat` | PDF.js page+quote highlight and recenter behavior | CP36 | **IDEA ONLY; README declares AGPL-3.0-only** |
| `one-pager-backend` | PDF.js page/search navigation pattern | CP36 | **IDEA ONLY; our provenance remains internal IDs/page/bbox** |
| `ExcelTableCreator / metric-search workbook paths` | Config-driven XLSX styling, notes/highlight review patterns | CP42 | **ADOPT selectively** |
| `excel-agent-harness` | Typed narrow tools over generic shell; resumable question/eval runs with verifier/token/cost records | CP44, CP46 | **ADOPT principles; no agent framework needed** |
| `bynd-ui` | Tokenized design system and linting against hardcoded shared styles | Existing frontend / future shared components | **PATTERN ONLY; package is UNLICENSED/private registry** |
| `financial-statement-extraction / metric-search-backend` | Queue-backed processing and worker operational patterns | CP18, CP47 | **REFERENCE ONLY; avoid domain-specific complexity** |

## Detailed adopted patterns

### 1. Typed outcomes instead of false booleans

`validation-service` separates a positive result, a strong negative, an inability to validate, and out-of-scope input. That distinction maps directly to tender extraction/evidence/compliance: a missing/unreadable source is not the same thing as evidence proving a mismatch.

**Plan effect:** CP31, CP50, CP54, CP55, and CP57 now require typed outcomes, stable reason codes, explicit missing-result handling, and safe abstention.

### 2. Content-addressed source extraction

`validation-engine` separates PDF byte caching from page-text caching and keys reusable page extraction to the actual PDF content hash, physical page, and extractor version. It checks schema/version/source identity and requested-page coverage before reuse.

**Plan effect:** CP24 now specifies content-hash + page + extractor-version cache identity, cache-schema versioning, coverage checks, and explicitly forbids treating cached semantic verdicts as immutable truth.

### 3. Provenance authority is passed down, not rediscovered

`validation-engine` centralizes page authority and intentionally ignores citation URL fragments as evidence authority. Deeper window/matcher code consumes the authorized pages instead of deciding where it is allowed to look.

**Plan effect:** CP27 and CP30 now require trusted document-version/page authority to flow into chunking and anchoring. Search/fuzzy matching may locate within an authorized page, never broaden source scope.

### 4. PDF text layers need a trust gate

`metric-search` demonstrates why 'PDF has extractable text' is insufficient: scans may have hidden OCR layers; text can be invisible, unmapped, covered, duplicated, or otherwise different from what a reader sees.

**Plan effect:** CP19 and CP21 now require reason-coded page trust checks and routing proven-untrustworthy native text to OCR instead of assuming all selectable text is authored text.

### 5. One document = one traceable background job

`final-final-chunking-pipeline` and the worker repos use a durable job identity, bounded consumers, per-stage logging, and isolated heavy work. `finance-data-ingestion-service` adds explicit retry budgets rather than infinite retries.

**Plan effect:** CP18 carries one job/correlation ID through the whole document lifecycle, uses bounded concurrency/prefetch, retry budgets, permanent-vs-transient errors, and stage timings.

### 6. Every expected target gets a result

`validation-service` explicitly settles missing/ambiguous handler outputs instead of letting missing rows look like successful absence. It fingerprints inputs so stale output is safer to recompute than reuse.

**Plan effect:** CP31 requires canonical input fingerprints and one-target-one-result semantics.

### 7. Eval architecture should be layered

`validation-engine` uses golden positives, golden negatives, mutation-generated negatives, historical regressions, stress cases, and API invariant cases, then compares runs and builds a correctness dashboard.

**Plan effect:** CP43–44 now specify the same *shape* of evaluation system for tender requirements/provenance—not the same datasets.

### 8. Privacy-safe telemetry and LLM cost are part of the product

`validation-service` uses an allowlist for structured telemetry and stable provider-error categories; `engineering-docs` requires every LLM call to carry run/model/token/cost metadata and every run to have a summary.

**Plan effect:** CP26 and CP46 now make LLM usage/cost and privacy-safe stage telemetry explicit acceptance work.

### 9. Auth security is more than JWT verification

`universal-auth-service` adds request IDs, trusted redirect origins, production/dev origin separation, CSP/security headers, and route-specific rate limiting. `company-reports-backend` provides useful organization/membership constraints and service-layer tenant resolution.

**Plan effect:** CP08 and CP45 now include these controls while keeping the actual auth provider replaceable.

### 10. Deployment should be explicit and immutable

`bynd-devops-system` separates long-running Container Apps from one-shot/event workers, uses immutable image tags and OIDC, and requires migrations before deploying a new image rather than on app startup.

**Plan effect:** CP07 and CP47 now encode those principles while leaving the exact cloud deployment provider-neutral until implementation.

### 11. OCR table context is useful, but auto-fixing is too risky here

`ocr-table-fixes-discovery` preserves original cell text, confidence, bounding boxes, and contextual formatting clues. Those metadata are valuable. Its automated corrections are intentionally **not** being copied because tender requirements cannot silently change technical values.

**Plan effect:** CP23 and CP33 adopt the metadata/diagnostic idea but keep ambiguous transformations as human-review flags.

### 12. Source viewers should keep the active evidence visible

`industry-report-agentic`, `table_grid`, `one-pager-backend`, and `chat` all contain evidence/PDF viewing ideas. A particularly useful interaction is re-centering a selected citation after async render/zoom/layout changes and navigating to a trusted page even if exact text highlighting cannot be recreated.

**Plan effect:** CP36 now standardizes immutable version + page + span/quote/bbox viewer inputs and explicit approximate/no-highlight fallback.

## Patterns deliberately rejected or deferred

| Pattern | Seen in | Why we are not adopting it now |
| --- | --- | --- |
| Agent-first orchestration | `Several report/agent repos` | This product needs deterministic document → requirement → review first. Agents add complexity before the boring pipeline works. |
| Vector DB/RAG in Phase 1 | `VectorDB, AzureAISearch, RAG-Calls, chunking experiments` | No OEM evidence retrieval exists in Phase 1; adding vector infrastructure now would be premature. |
| Aggressive OCR auto-correction | `ocr-table-fixes-discovery and older extraction experiments` | Tender meaning must not be silently changed. Use confidence/reason diagnostics and human review instead. |
| Boolean-only validation | `older validation-engine public shape` | Collapses absence, source failure, out-of-scope, and engine failure. Use typed statuses/reason codes. |
| URL fragments as provenance | `older citation/search patterns` | Navigation hints are not source authority. Immutable document version/page records are authoritative. |
| App-startup schema creation/migration | `some service bootstrap patterns` | Use Alembic as an explicit deploy operation; avoid multi-replica races. |
| Cached semantic verdicts as source truth | `tempting optimization` | Only cache source/derived extraction keyed by content/version; re-evaluate semantic decisions when inputs/config change. |
| Direct dependency on private Bynd UI/auth/services | `bynd-ui, universal-auth deployment` | Personal product must remain self-contained/provider-neutral unless an explicit ownership/access decision changes that. |
| Copying AGPL implementation code | `chat` | README declares AGPL-3.0-only; interaction ideas may inform a fresh implementation but code should not be copied into this proprietary repo. |
| Blind reuse of historical experiments | `PDF/table/chunking prototypes` | Use them as edge-case/test inspiration; benchmark current libraries/providers rather than inheriting old implementation choices. |

## What this changes in the canonical checkpoint plan

The checkpoint numbers and order stay stable. This audit adds implementation guidance inside the existing checkpoints rather than creating a parallel roadmap. The next checkpoint remains **CP11 — Real project dashboard and project progress**.

Updated checkpoints: **CP06, CP07, CP08, CP09, CP10, CP18, CP19, CP21, CP22, CP23, CP24, CP26, CP27, CP30, CP31, CP33, CP36, CP42, CP43, CP44, CP45, CP46, CP47, CP50, CP54, CP55, CP56, CP57**.

## Complete Bynd repository inventory

| # | Repository | Audit disposition |
| ---: | --- | --- |
| 1 | `Bynd-ai/MainReportBuildingApplication` | UI/product reference; existing design direction already absorbs most useful patterns |
| 2 | `Bynd-ai/tableGraphProcessing` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 3 | `Bynd-ai/Subheading_Heading_detection` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 4 | `Bynd-ai/NSE-data-scraping` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 5 | `Bynd-ai/universal-auth-service` | Deep-reviewed; direct reference patterns |
| 6 | `Bynd-ai/alerts-analytics-frontend` | UI/product reference; existing design direction already absorbs most useful patterns |
| 7 | `Bynd-ai/bynd-ui` | Deep-reviewed; direct reference patterns |
| 8 | `Bynd-ai/ocr-table-fixes-discovery` | Deep-reviewed; direct reference patterns |
| 9 | `Bynd-ai/MonitoringAlerts` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 10 | `Bynd-ai/Bynd-unified-prototype` | UI/product reference; existing design direction already absorbs most useful patterns |
| 11 | `Bynd-ai/report_gen` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 12 | `Bynd-ai/Summarizer` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 13 | `Bynd-ai/addin-icons` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 14 | `Bynd-ai/hdfc_data_push_function` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 15 | `Bynd-ai/double_sided_pdf_splitter_function` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 16 | `Bynd-ai/micro_frontend_report` | UI/product reference; existing design direction already absorbs most useful patterns |
| 17 | `Bynd-ai/bynd_microservice` | Operational/eval/job reference; selective ideas only |
| 18 | `Bynd-ai/Bynd-Alerts-VM` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 19 | `Bynd-ai/reportAppPrototype` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 20 | `Bynd-ai/bynd_backend` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 21 | `Bynd-ai/company_classification_dashboard` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 22 | `Bynd-ai/validation-engine` | Deep-reviewed; direct reference patterns |
| 23 | `Bynd-ai/metric_search_frontend` | UI/product reference; existing design direction already absorbs most useful patterns |
| 24 | `Bynd-ai/company-reports-frontend` | UI/product reference; existing design direction already absorbs most useful patterns |
| 25 | `Bynd-ai/final-final-chunking-pipeline` | Deep-reviewed; direct reference patterns |
| 26 | `Bynd-ai/one-pager-backend` | Deep-reviewed; direct reference patterns |
| 27 | `Bynd-ai/NSE-Scraping-Prototype` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 28 | `Bynd-ai/bynd_metric_frontend` | UI/product reference; existing design direction already absorbs most useful patterns |
| 29 | `Bynd-ai/GlobeApp` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 30 | `Bynd-ai/MCA_Automation` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 31 | `Bynd-ai/admin` | UI/product reference; existing design direction already absorbs most useful patterns |
| 32 | `Bynd-ai/indian-company-cin-industry-finder` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 33 | `Bynd-ai/ContinuousTableMerging` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 34 | `Bynd-ai/metric-search` | Deep-reviewed; direct reference patterns |
| 35 | `Bynd-ai/TopicSummary` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 36 | `Bynd-ai/peer_workflow_final` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 37 | `Bynd-ai/intelAdmin` | UI/product reference; existing design direction already absorbs most useful patterns |
| 38 | `Bynd-ai/industry-reports` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 39 | `Bynd-ai/cheap-chunking` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 40 | `Bynd-ai/join-fin-stmnt-jobs` | Operational/eval/job reference; selective ideas only |
| 41 | `Bynd-ai/bynd_ocr` | No material implementation found |
| 42 | `Bynd-ai/PDF-AI3` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 43 | `Bynd-ai/PDF-AI2` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 44 | `Bynd-ai/OperatingMetricExtractor` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 45 | `Bynd-ai/validation-service` | Deep-reviewed; direct reference patterns |
| 46 | `Bynd-ai/company-reports-backend` | Deep-reviewed; direct reference patterns |
| 47 | `Bynd-ai/table_detection_microsoft` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 48 | `Bynd-ai/similar-join-tables` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 49 | `Bynd-ai/LLMsherpa` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 50 | `Bynd-ai/Alerts` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 51 | `Bynd-ai/Bynd-shell` | UI/product reference; existing design direction already absorbs most useful patterns |
| 52 | `Bynd-ai/excel-financial-statement-parser` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 53 | `Bynd-ai/Index_Parsing` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 54 | `Bynd-ai/fin-stat-extraction-jobs` | Operational/eval/job reference; selective ideas only |
| 55 | `Bynd-ai/business-standard-broker-report-scraping` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 56 | `Bynd-ai/Table-Chunking` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 57 | `Bynd-ai/Table-Extraction-azure` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 58 | `Bynd-ai/VectorDB` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 59 | `Bynd-ai/Statements-from-PDF` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 60 | `Bynd-ai/SummaryFrontend` | UI/product reference; existing design direction already absorbs most useful patterns |
| 61 | `Bynd-ai/reportGeneration_frontend` | UI/product reference; existing design direction already absorbs most useful patterns |
| 62 | `Bynd-ai/Evals_dataset` | Operational/eval/job reference; selective ideas only |
| 63 | `Bynd-ai/chat` | Deep-reviewed; direct reference patterns |
| 64 | `Bynd-ai/ChartCreationExperiment` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 65 | `Bynd-ai/data-pipelines` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 66 | `Bynd-ai/DRHP` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 67 | `Bynd-ai/RAG-Calls` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 68 | `Bynd-ai/workflows` | Operational/eval/job reference; selective ideas only |
| 69 | `Bynd-ai/excel-table-download` | No material implementation found |
| 70 | `Bynd-ai/ExcelTableCreator` | Deep-reviewed; direct reference patterns |
| 71 | `Bynd-ai/table_grid` | Deep-reviewed; direct reference patterns |
| 72 | `Bynd-ai/PDF-AI` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 73 | `Bynd-ai/backend` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 74 | `Bynd-ai/slack-alerts-code` | Operational/eval/job reference; selective ideas only |
| 75 | `Bynd-ai/financial-statement-extraction` | Deep-reviewed; direct reference patterns |
| 76 | `Bynd-ai/scraping_company_data` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 77 | `Bynd-ai/industry-report-agentic` | Deep-reviewed; direct reference patterns |
| 78 | `Bynd-ai/metric-search-backend` | Deep-reviewed; direct reference patterns |
| 79 | `Bynd-ai/bynd-devops-system` | Deep-reviewed; direct reference patterns |
| 80 | `Bynd-ai/PDF_AI` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 81 | `Bynd-ai/vault-frontend` | UI/product reference; existing design direction already absorbs most useful patterns |
| 82 | `Bynd-ai/image-finder` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 83 | `Bynd-ai/Bynd-Alerts-Azure` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 84 | `Bynd-ai/peer_workflow_research` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 85 | `Bynd-ai/onepager-console` | Operational/eval/job reference; selective ideas only |
| 86 | `Bynd-ai/table_insight` | Deep-reviewed; direct reference patterns |
| 87 | `Bynd-ai/workflows-frontend` | UI/product reference; existing design direction already absorbs most useful patterns |
| 88 | `Bynd-ai/testTableMergingPrompt` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 89 | `Bynd-ai/reportGen_frontend` | UI/product reference; existing design direction already absorbs most useful patterns |
| 90 | `Bynd-ai/AlertsApp` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 91 | `Bynd-ai/tableMerging` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 92 | `Bynd-ai/ai-summary-generator` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 93 | `Bynd-ai/ReportGenerationApp` | UI/product reference; existing design direction already absorbs most useful patterns |
| 94 | `Bynd-ai/chunkingPipelineExperiments` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 95 | `Bynd-ai/companies-metadata-enrichment` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 96 | `Bynd-ai/engineering-docs` | Deep-reviewed; direct reference patterns |
| 97 | `Bynd-ai/excel-agent-harness` | Deep-reviewed; direct reference patterns |
| 98 | `Bynd-ai/intel-admin` | UI/product reference; existing design direction already absorbs most useful patterns |
| 99 | `Bynd-ai/Table-Extraction` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 100 | `Bynd-ai/AzureAISearch` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 101 | `Bynd-ai/nse-scraper` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 102 | `Bynd-ai/company-reports-agent` | Deep-reviewed; direct reference patterns |
| 103 | `Bynd-ai/finance-data-ingestion-service` | Deep-reviewed; direct reference patterns |
| 104 | `Bynd-ai/ByndConsumptionFunctionApp` | Inventory-reviewed; domain-specific or low overlap with core tender workflow |
| 105 | `Bynd-ai/IndexExtractionFunction` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 106 | `Bynd-ai/bynd_frontend` | UI/product reference; existing design direction already absorbs most useful patterns |
| 107 | `Bynd-ai/chunking-pipeline` | Document/OCR/table/retrieval experiment; useful for benchmarks/edge cases, not a direct dependency |
| 108 | `Bynd-ai/chunking_process` | Deep-reviewed; direct reference patterns |

## How to use this audit while implementing

1. Start from the first unchecked item in `checkpoint.md`.
2. If that checkpoint has **Bynd reuse notes**, use the named repositories as design/test references.
3. Re-verify the referenced implementation before relying on a detail; these repositories evolve.
4. Implement the behavior fresh inside this repo's own adapters/services unless a concrete, license-compatible code-reuse decision is made.
5. If a referenced pattern conflicts with the Tender Compliance trust model, the trust model wins.
6. Add any newly discovered useful Bynd pattern to this audit and its relevant checkpoint in the same PR.

## Bottom line

The most reusable Bynd assets are not agents or RAG components. They are the boring production disciplines around **source authority, typed uncertainty, content-addressed extraction, PDF/OCR trust, bounded workers, deterministic contracts, layered evals, privacy-safe telemetry, tenant boundaries, and explicit deployment/migrations**. Those are now incorporated into the project plan.
