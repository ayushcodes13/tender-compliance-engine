# Deployment Runbook (CP47)

## Overview

The Tender Compliance Engine is deployed as three services: API, worker,
and web frontend, backed by PostgreSQL, Redis, and MinIO (S3-compatible
object storage).

## Architecture

```
                    ┌─────────────┐
                    │   Client    │
                    └──────┬──────┘
                           │  HTTPS
                           ▼
                    ┌─────────────┐
                    │  Web (3000) │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  API (8000) │
                    └──────┬──────┘
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐ ┌─────────┐ ┌──────────┐
        │ Postgre │ │  Redis  │ │  MinIO   │
        │ SQL 5432│ │ 6379    │ │ 9000     │
        └─────────┘ └─────────┘ └──────────┘
              ▲
              │
        ┌─────────┐
        │ Worker  │
        └─────────┘
```

## Environment Configuration

All configuration comes from environment variables (see
`apps/api/.env.example`).  No secrets are in config files.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `OBJECT_STORAGE_ENDPOINT` | No | — | S3-compatible endpoint (empty = fake) |
| `REDIS_URL` | No | — | Redis connection string (empty = fake) |
| `OPENAI_API_KEY` | No | — | OpenAI API key for LLM extraction |
| `CORS_ALLOWED_ORIGINS` | Yes | — | Comma-separated allowed web origins |

## Process Commands

### API
```bash
python -m tender_compliance_api.main
# Or with uvicorn:
uvicorn tender_compliance_api.main:app --host 0.0.0.0 --port 8000
```

Health check: `GET /health` → `{"status": "ok", "service": "tender-compliance-api"}`

### Worker
```bash
python -m tender_compliance_worker --max-concurrency 4
```

The worker dequeues document-processing jobs from Redis, processes them
(PARSE → OCR → CLEANUP → EXTRACT stages), and handles retries/acknowledgements.

### Web Frontend
```bash
npm run dev   # development
npm run build && npm start   # production
```

## Migrations

Migrations are managed by Alembic and must be run explicitly before
deploying a new API version.

### Apply migrations
```bash
cd apps/api
alembic upgrade head
```

### Check current version
```bash
alembic current
```

### Create a new migration
```bash
alembic revision -m "CPNN — description"
```

### Migration job (containerized deployment)
In a container orchestration system, run migrations as a one-shot
init-container or job BEFORE starting the API:

```yaml
initContainers:
  - name: migrate
    image: ghcr.io/your-org/tender-compliance-api:v1.2.3
    command: ["alembic", "upgrade", "head"]
    envFrom:
      - secretRef:
          name: tce-secrets
      - configMapRef:
          name: tce-config
```

### Backup before migration
Always take a PostgreSQL base backup before applying schema migrations:
```bash
pg_dump -h postgres -U tce tce > backup-$(date +%Y%m%d-%H%M%S).sql
```

## Rollback Procedures

### Application rollback (code)
```bash
# Redeploy the previous image tag
kubectl set image deployment/api api=ghcr.io/your-org/tender-compliance-api:v1.2.2
```

### Schema rollback
```bash
# Downgrade one revision
alembic downgrade -1

# Or downgrade to a specific revision
alembic downgrade 0017_export_artifacts
```

**Warning**: Schema downgrades may lose data if newer migrations added
columns/tables with existing data.  Always restore from backup rather
than downgrading when data loss is possible.

### Failed deployment rollback
1. Redeploy the previous container image.
2. If the schema was migrated, downgrade to the previous revision.
3. If data was lost, restore from the most recent backup.

## TLS and CORS

- TLS is terminated at the reverse proxy / load balancer (nginx, Caddy,
  or cloud LB).  The API does not serve TLS directly.
- CORS is enforced via `CORS_ALLOWED_ORIGINS` environment variable.
- The API sets security headers: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`.

## Secrets Management

**Never commit secrets.**  Use one of:
- Environment variables injected by the orchestration platform
- A secrets manager (AWS Secrets Manager, GCP Secret Manager, etc.)
- GitHub OIDC / workload identity for cloud provider credentials

For local development, use `.env` files (git-ignored).  For production,
use the orchestration platform's secrets injection.

## Failed-Job Recovery

When a worker fails to process a job:

1. The job is automatically retried up to `MAX_RETRIES` (default: 5).
2. After max retries, the `DocumentVersion.processing_status` is set to
   `FAILED` and the `ProcessingRun` table records the error type/category.
3. Manual recovery: POST to `versions/{ver}/retry` to re-enqueue the job.
4. To find failed jobs:
   ```bash
   python -c "
   from tender_compliance_api.db.session import get_session
   from sqlalchemy import select
   from tender_compliance_api.db.models import DocumentVersion, DocumentProcessingStatus
   async with get_session() as s:
       result = await s.execute(
           select(DocumentVersion).where(
               DocumentVersion.processing_status == DocumentProcessingStatus.FAILED
           )
       )
       for v in result.scalars():
           print(v.id, v.processing_status)
   "
   ```

## Worker Scaling

Workers are stateless and can be scaled horizontally:

```bash
# Scale to N workers
python -m tender_compliance_worker --max-concurrency N

# In Kubernetes, adjust the replica count:
kubectl scale deployment/worker --replicas=3
```

Each worker claims jobs from Redis via visibility-timeout locking.
Additional workers automatically pick up pending jobs.

Monitor: `GET /metrics` for `queue_depth` and `job_failures_total`.

## Deployment Smoke Tests

Run after deployment to verify:

```bash
#!/bin/bash
set -e

API_URL="${API_URL:-http://localhost:8000}"

# 1. Health check
echo "Checking health..."
curl -sf "${API_URL}/health" | python -c "import sys,json; assert json.load(sys.stdin)['status']=='ok'"

# 2. Auth denied without headers
echo "Checking auth..."
curl -sf -o /dev/null -w "%{http_code}" "${API_URL}/projects" | grep -q 401

# 3. Metrics endpoint
echo "Checking metrics..."
curl -sf "${API_URL}/metrics" | python -c "import sys,json; d=json.load(sys.stdin); assert 'gauges' in d"

# 4. Migration head is current
echo "Checking migration version..."
cd apps/api && alembic current

echo "All smoke tests passed."
```

## Production Checklist

Before cutting over:
- [ ] All environment variables set (DATABASE_URL, STORAGE credentials, etc.)
- [ ] CORS origins configured for production domain
- [ ] TLS configured at the proxy layer
- [ ] Migrations applied: `alembic upgrade head`
- [ ] Health check passes: `GET /health`
- [ ] Database backup configured (WAL archiving + periodic base backup)
- [ ] Object storage bucket versioning enabled
- [ ] Worker process running and consuming from Redis
- [ ] Smoke tests pass
- [ ] Rollback plan documented

## Local development with docker-compose

The repository-root `docker-compose.yml` provides a full local stack (postgres,
redis, minio, api, worker, web). It uses inline environment variables matching
the service names, so `docker-compose up --build` works out of the box:

```bash
docker compose up --build
# API:      http://localhost:8000
# Web:      http://localhost:3000
# MinIO:    http://localhost:9000  (console: http://localhost:9001)
```

Before uploading real documents, apply migrations:

```bash
docker compose exec api alembic upgrade head
```

For infrastructure-only (no api/worker/web containers), use the Makefile target:
`make infra-up` (uses `infra/docker-compose.yml`). The app services are then
started locally via `make api-dev` and `npm run dev` (apps/web).
