# Backup, Retention, and Deletion Runbook (CP46)

## Overview

This document describes how Tender Compliance Engine manages data lifecycle:
backup strategy, retention policy, and authorized hard deletion.

## Backup Strategy

### Database (PostgreSQL)

- **Continuous archiving**: Enable WAL (Write-Ahead Logging) archiving to an
  encrypted bucket.  Use `pg_basebackup` for base backups weekly and WAL
  archiving for point-in-time recovery (PITR).
- **Retention**: Keep base backups for 30 days; WAL segments for 7 days
  beyond the oldest base backup needed for PITR.
- **Test restore**: Perform a monthly restore-into-staging drill with
  non-production data.  Verify that metadata and object-reference consistency
  is preserved.
- **Backup command**:
  ```bash
  pg_basebackup -D /backups/pg_base -Fp -Xs -P -R
  ```

### Object Storage (MinIO/S3)

- **Versioning**: Enable bucket versioning.  All object writes are
  append-only (immutable DocumentVersions); deletions are
  version-expiration rules, not in-place overwrites.
- **Replication**: Enable cross-region replication of the
  `tender-documents` bucket to a disaster-recovery region.
- **Retention**: Originals retained 90 days after project archival or
  hard deletion.  Rendered assets (page images, OCR output) retained 30 days.
  Export artifacts retained 30 days.

### Audit Logs

- Audit log rows live in the same PostgreSQL database as application data
  and are included in WAL-archiving backups.
- Audit retention is separate from data retention: audit entries are
  retained for 7 years (or as required by contract law) and are NOT
  subject to the 90-day data retention policy.

## Retention Policy

| Asset type              | Retention period | Trigger                      |
|-------------------------|------------------|------------------------------|
| Original tender documents | 90 days        | After hard deletion of project |
| Rendered page images    | 30 days          | After project archival       |
| OCR/parser output       | 30 days          | After project archival       |
| Export artifacts (XLSX) | 30 days          | After generation             |
| Audit logs              | 7 years (config) | N/A                          |

### How retention deadlines are set

When a project is archived, a `retention_deadline` is set on each
`DocumentVersion` to `now + retention_originals_days` (default 90 days).
After the deadline passes, the stored object becomes eligible for
physical deletion from object storage.

### Running the cleanup job

```bash
# Dry run (default — reports eligible objects without deleting)
python -m tender_compliance_api.retention --dry-run

# Apply deletions
python -m tender_compliance_api.retention --apply

# Single-tenant cleanup
python -m tender_compliance_api.retention --apply --organization-id <uuid>
```

Schedule (e.g., in Kubernetes CronJob):
```yaml
schedule: "0 2 * * *"  # daily at 02:00 UTC
```

## Hard Deletion

### API

```http
DELETE /projects/{project_id}
Authorization: <auth headers>
x-correlation-id: <optional trace ID>
```

- Only **archived** projects can be hard-deleted (returns 409 otherwise).
- Only the owning organization can perform deletion (returns 404 for other
  tenants).
- All data is removed from PostgreSQL via `ON DELETE CASCADE`.
- Stored object bytes are deleted from object storage.
- An audit log entry is written with the correlation ID and actor.

### Manual (database-level)

If the API is unavailable, deletion can be performed directly:

```sql
BEGIN;
-- Verify ownership and archived status
SELECT id FROM projects
  WHERE id = '<project_id>'
  AND organization_id = '<org_id>'
  AND status = 'archived';

-- Delete stored object keys for physical deletion
SELECT storage_key FROM stored_objects WHERE project_id = '<project_id>';

-- Delete the project (CASCADE handles documents, versions, requirements, etc.)
DELETE FROM projects WHERE id = '<project_id>';
COMMIT;
```

After the DB transaction, manually delete the storage objects using the
keys retrieved above.

## Monitoring

### Metrics endpoints

```
GET /health  — liveness check
GET /metrics — point-in-time metrics snapshot (counters, gauges, histograms)
```

### Key metrics to alert on

| Metric                      | Threshold         | Action              |
|-----------------------------|--------------------|---------------------|
| `job_failures_total`        | > 5 in 5 minutes   | Page on-call        |
| `queue_depth` gauge         | > 100 for 10 min   | Scale workers       |
| `job_latency_seconds` (avg) | > 300s for 5 min   | Investigate         |
| `extraction_failures_total` | > 10 in 5 minutes  | Check LLM provider  |
| `ocr_failures_total`        | > 10 in 5 minutes  | Check Tesseract     |

### Log query examples (JSON-structured logs)

```bash
# Find all hard deletions for a project
grep "project_hard_deleted" | jq '.correlation_id'

# Find storage delete failures
grep "storage_delete_failed"

# Audit trail for a project
grep "project.hard_delete" | jq 'select(.entity_id == "<project_id>")'
```
