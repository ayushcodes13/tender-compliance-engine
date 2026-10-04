# Deployment Runbook

## Two deployment modes

Tender Compliance Engine deliberately has two deployment modes so the first
customer does not require a full SaaS platform.

### 1. Private pilot / one-customer deployment

Use the repository-root `docker-compose.yml`.

The stack starts:

- PostgreSQL;
- Redis;
- a shared durable filesystem volume for source files and exports;
- Alembic migrations;
- FastAPI API;
- background OCR/document worker;
- Next.js web app.

The backend runs in `single_workspace` mode. The browser talks only to the
web app; Next.js proxies API traffic over the internal container network.

The only **external secret** required by this bundled pilot is
`OPENAI_API_KEY`. PostgreSQL/Redis run locally in Compose and document bytes
persist in the named `object_data` volume shared by API and worker.

```bash
cp .env.example .env
# set OPENAI_API_KEY in .env
docker compose config   # fails immediately if the key is still empty
docker compose up --build
```

Open: **http://localhost:3000**

Readiness through the same path used by the browser:

```bash
curl -fsS http://localhost:3000/api/backend/ready
```

The API binds to localhost in this mode; the browser uses the same-origin
Next.js proxy and the shared document volume is internal to the Docker stack.

### 2. Public multi-customer SaaS

Do not expose the private-pilot defaults directly to the internet.

Before public multi-tenant launch, replace the bundled defaults with:

- a real identity provider instead of `single_workspace`;
- managed/generated database, Redis, and object-storage credentials;
- a secrets manager;
- TLS and a real domain;
- managed backups/retention;
- production monitoring/error reporting;
- malware scanning appropriate to the deployment.

These are operational upgrades, not prerequisites for selling/running a
private one-customer pilot.

## Runtime architecture

```text
Browser
   │
   ▼
Next.js web
   │  /api/backend/* (same origin)
   ▼
FastAPI API ───── PostgreSQL
   │
   ├───────────── Redis
   └──── shared object_data volume ────┐
                                       │
                                    Worker
                               parser / OCR / LLM
```

## Readiness vs health

- `GET /health` — process liveness.
- `GET /ready` — checks the dependencies needed to serve the product,
  including database, queue, durable document storage, and production AI
configuration.
- Browser/deployment checks should prefer
  `GET /api/backend/ready` through the web app because that proves both the
  frontend proxy and backend dependencies are reachable.

## Migrations

Alembic is the schema source of truth.

The bundled Compose stack runs the `migrate` service **before** the API starts:

```text
PostgreSQL healthy
      ↓
alembic upgrade head
      ↓
API / worker
      ↓
web
```

For a separately orchestrated production deployment, keep the same ordering:
run a one-shot migration job before deploying the new API image. Do not run
schema creation/migrations from every API replica at application startup.

CI also applies the complete migration chain to PostgreSQL 16 and performs a
real ORM insert so SQLite cannot hide PostgreSQL-specific enum/default issues.

## Secrets

Never commit secrets.

Private pilot:

```text
OPENAI_API_KEY=<real key>
```

The remaining values in `.env.example` have bundled local defaults. Cloud
deployments can opt into the existing S3-compatible adapter by setting
`OBJECT_STORAGE_ENDPOINT` plus credentials. Change all bundled defaults before
exposing infrastructure outside a trusted pilot host.

Public deployment should inject all secrets through the deployment platform or
a secrets manager.

## Backups

Before production schema changes, back up PostgreSQL. Back up the
`object_data` volume independently because it contains originals, rendered
pages, and generated exports.

Example database backup for the bundled stack:

```bash
docker compose exec -T postgres \
  pg_dump -U tce tce > "tce-$(date +%Y%m%d-%H%M%S).sql"
```

Named Docker volumes keep pilot data across restarts. `docker compose down -v`
**deletes** those volumes; do not use `-v` on a customer system unless deletion
is intentional.

## Failed document jobs

Document jobs have explicit persisted processing states and bounded retries.
A failed job remains visible as failed instead of turning into an empty or
fabricated compliance result. Use the supported retry endpoint/UI action after
fixing the underlying source/provider problem.

## Scaling

The current commercial target does not require a microservice mesh.

- API/web can be replicated when needed.
- Workers are stateless job consumers and can be scaled horizontally.
- Keep one-document job isolation and bounded worker concurrency.

Scale only after real pilot load demonstrates a bottleneck.

## Release verification

Required automated release checks:

- PostgreSQL full migration + ORM enum smoke;
- backend test/evaluation suite;
- zero-false-compliance critical gates;
- frontend typecheck + production build;
- API, worker, and web container builds;
- full bundled Compose startup;
- `http://localhost:3000/api/backend/ready` returns `status=ready`.

After those checks, use
[POST61_RELEASE_REVIEW.md](../POST61_RELEASE_REVIEW.md) with real customer-like
documents before calling a release accepted.
