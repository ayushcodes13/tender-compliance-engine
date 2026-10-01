"""Tests for CP46 — Observability, logging, metrics, retention, and deletion.

Covers:
- Structured JSON logging with correlation IDs
- Log privacy: confidential fields are never logged
- Metrics registry: counters, gauges, histograms
- Retention deadline evaluation and physical deletion
- Hard project deletion (audit, cascade, tenant isolation)
- Filename sanitization already tested in test_security_uploads.py
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from tender_compliance_api.config import get_settings
from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    Project,
    ProjectStatus,
    StoredObject,
    TenderDocument,
    User,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.logs import (
    StructuredJsonFormatter,
    get_correlation_id,
    set_correlation_id,
)
from tender_compliance_api.main import app
from tender_compliance_api.metrics import Timer, get_metrics
from tender_compliance_api.retention import RetentionService

client = TestClient(app)
_session_cm = contextlib.asynccontextmanager(get_session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _build_org_project_archived() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create an archived project owned by Org A."""
    org_a = uuid.uuid4()
    user_a = uuid.uuid4()
    project_id = uuid.uuid4()

    async def _setup():
        async with _session_cm() as session:
            session.add(Organization(id=org_a, name="Org A"))
            session.add(
                User(
                    id=user_a,
                    auth_provider="dev",
                    auth_provider_user_id=str(user_a),
                )
            )
            session.add(
                Membership(organization_id=org_a, user_id=user_a, role="owner")
            )
            session.add(
                Project(
                    id=project_id,
                    organization_id=org_a,
                    name="Org A Archived",
                    status=ProjectStatus.ARCHIVED,
                    created_by=user_a,
                )
            )
            doc = TenderDocument(
                project_id=project_id,
                display_name="tender.pdf",
                document_type="tender",
            )
            session.add(doc)
            await session.flush()
            version = DocumentVersion(
                id=uuid.uuid4(),
                document_id=doc.id,
                version_number=1,
                stored_object_id=uuid.uuid4(),
                sha256="abc123",
                mime_type="application/pdf",
                size_bytes=1024,
                processing_status=DocumentProcessingStatus.PARSED,
            )
            session.add(version)
            await session.flush()
            stored = StoredObject(
                id=version.stored_object_id,
                organization_id=org_a,
                project_id=project_id,
                document_id=doc.id,
                storage_key=f"test/{version.stored_object_id}.pdf",
                filename="tender.pdf",
                content_type="application/pdf",
                content_length=1024,
                checksum_sha256="abc123",
                etag="etag1",
            )
            session.add(stored)
            await session.commit()
            return user_a, org_a, project_id

    return asyncio.run(_setup())


def _build_org_b_user() -> tuple[uuid.UUID, uuid.UUID]:
    org_b = uuid.uuid4()
    user_b = uuid.uuid4()

    async def _setup():
        async with _session_cm() as session:
            session.add(Organization(id=org_b, name="Org B"))
            session.add(
                User(
                    id=user_b,
                    auth_provider="dev",
                    auth_provider_user_id=str(user_b),
                )
            )
            session.add(
                Membership(organization_id=org_b, user_id=user_b, role="owner")
            )
            await session.commit()

    asyncio.run(_setup())
    return user_b, org_b


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


class TestStructuredLogging:
    def test_correlation_id_generated_and_propagated(self):
        """A correlation ID is generated and available via get_correlation_id."""
        cid = set_correlation_id()
        assert cid is not None
        assert len(cid) > 0
        assert get_correlation_id() == cid

    def test_correlation_id_propagated_from_header(self):
        """A client-provided correlation ID is honored."""
        requested = "client-req-12345"
        cid = set_correlation_id(requested)
        assert cid == requested

    def test_json_formatter_produces_valid_json(self):
        """The StructuredJsonFormatter outputs valid JSON with expected fields."""
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=1,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "hello world"
        assert data["level"] == "INFO"
        assert data["logger"] == "test"
        assert data["correlation_id"] is not None

    def test_privacy_unsafe_fields_filtered(self):
        """Privacy-unsafe field keys are never included in log output."""
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        record.extra_fields = {  # type: ignore[attr-defined]
            "document_body": "SECRET CONTENT",
            "raw_source": "also secret",
            "api_key": "sk-12345",
            "safe_field": "ok",
        }
        output = formatter.format(record)
        data = json.loads(output)
        assert "document_body" not in data
        assert "raw_source" not in data
        assert "api_key" not in data
        assert data["safe_field"] == "ok"

    def test_error_category_not_raw_message(self):
        """Exception info produces a stable error_category, not the raw
        exception message (which may contain confidential data)."""
        formatter = StructuredJsonFormatter()
        try:
            raise ValueError("CONFIDENTIAL: user data breach detected")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="",
                lineno=1,
                msg="something failed",
                args=(),
                exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["error_type"] == "ValueError"
        assert data["error_category"] == "runtime_error"
        # The confidential message must NOT appear in the output
        assert "CONFIDENTIAL" not in output
        assert "breach" not in output

    def test_middleware_injects_correlation_id(self):
        """The correlation ID middleware sets x-correlation-id header."""
        response = client.get("/health", headers={})
        assert response.status_code == 200
        assert "x-correlation-id" in response.headers

    def test_middleware_propagates_client_id(self):
        """A client-supplied correlation ID is echoed back."""
        requested = "client-trace-001"
        response = client.get(
            "/health",
            headers={"x-correlation-id": requested},
        )
        assert response.status_code == 200
        assert response.headers["x-correlation-id"] == requested


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    def setup_method(self):
        """Reset the metrics registry before each test."""
        from tender_compliance_api import metrics as metrics_mod

        metrics_mod._METRICS.clear()
        metrics_mod._GAUGES.clear()
        metrics_mod._HISTOGRAMS.clear()
        metrics_mod._instance = None

    def test_counter_increments(self):
        reg = get_metrics()
        c = reg.counter("jobs_total", "Total jobs processed", labels={"stage": "parse"})
        assert c.value == 0
        c.inc()
        assert c.value == 1
        c.inc(5)
        assert c.value == 6

    def test_gauge_sets(self):
        reg = get_metrics()
        g = reg.gauge("queue_depth", "Pending queue items")
        g.set(42)
        assert g.value == 42.0
        g.inc(8)
        assert g.value == 50.0

    def test_histogram_records(self):
        reg = get_metrics()
        h = reg.histogram("latency_seconds", "Latency distribution")
        h.observe(0.5)
        h.observe(1.5)
        snap = reg.snapshot()
        hist = snap["histograms"][0]
        assert hist["count"] == 2
        assert hist["total_seconds"] == 2.0
        assert hist["min_seconds"] == 0.5
        assert hist["max_seconds"] == 1.5
        assert hist["avg_seconds"] == 1.0

    def test_timer_context_manager(self):
        reg = get_metrics()
        h = reg.histogram("job_latency", "Job latency")
        with Timer(h):
            pass
        snap = reg.snapshot()
        assert snap["histograms"][0]["count"] == 1
        assert snap["histograms"][0]["total_seconds"] >= 0.0

    def test_convenience_metrics(self):
        from tender_compliance_api.metrics import (
            metrics_extraction_failures,
            metrics_job_failures,
            metrics_ocr_failures,
            metrics_queue_depth,
            metrics_retention_deleted,
        )
        q = metrics_queue_depth()
        q.set(3)
        f = metrics_job_failures()
        f.inc()
        e = metrics_extraction_failures()
        e.inc(2)
        o = metrics_ocr_failures()
        o.inc()
        r = metrics_retention_deleted()
        r.inc(5)
        snap = get_metrics().snapshot()
        assert len(snap["counters"]) == 4
        assert len(snap["gauges"]) == 1

    def test_metrics_endpoint(self):
        """GET /metrics returns the registry snapshot."""
        reg = get_metrics()
        reg.counter("test_metric_total", "A test counter")
        response = client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "counters" in data
        assert "gauges" in data
        assert "histograms" in data

    def test_retention_counter_increments(self):
        reg = get_metrics()
        before = sum(
            c["value"] for c in reg.snapshot()["counters"]
            if c["name"] == "retention_deleted_total"
        )
        metrics = get_metrics()
        metrics.counter("retention_deleted_total", "Deleted objects").inc(3)
        after = sum(
            c["value"] for c in reg.snapshot()["counters"]
            if c["name"] == "retention_deleted_total"
        )
        assert after == before + 3


# ---------------------------------------------------------------------------
# Retention service
# ---------------------------------------------------------------------------


class TestRetentionService:
    def test_retention_deadline_eligible_for_deletion(self):
        """A version with a past retention_deadline on an archived project
        is eligible for physical deletion."""
        user_a, org_a, project_id = _build_org_project_archived()
        past = datetime.now(UTC) - timedelta(days=1)

        async def _set_deadline():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).join(Project)
                    .where(Project.organization_id == org_a)
                )
                ver = result.scalar_one()
                ver.retention_deadline = past
                await session.commit()
                return ver.id

        ver_id = asyncio.run(_set_deadline())

        async def _evaluate():
            async with _session_cm() as session:
                svc = RetentionService(session)
                eligible = await svc.evaluate_retention_deadlines(
                    organization_id=org_a
                )
                return eligible

        eligible = asyncio.run(_evaluate())
        assert ver_id in eligible or len(eligible) >= 1

    def test_retention_deadline_not_yet_eligible(self):
        """A version whose retention_deadline is in the future is NOT eligible."""
        user_a, org_a, project_id = _build_org_project_archived()
        future = datetime.now(UTC) + timedelta(days=30)

        async def _set_deadline():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).join(Project)
                    .where(Project.organization_id == org_a)
                )
                ver = result.scalar_one()
                ver.retention_deadline = future
                await session.commit()
                return ver.id

        asyncio.run(_set_deadline())

        async def _evaluate():
            async with _session_cm() as session:
                svc = RetentionService(session)
                return await svc.evaluate_retention_deadlines(
                    organization_id=org_a
                )

        eligible = asyncio.run(_evaluate())
        assert len(eligible) == 0

    def test_retention_tenant_isolation(self):
        """Org B cannot see Org A's retention-eligible versions."""
        user_a, org_a, project_id = _build_org_project_archived()
        past = datetime.now(UTC) - timedelta(days=1)

        async def _set_deadline():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).join(Project)
                    .where(Project.organization_id == org_a)
                )
                ver = result.scalar_one()
                ver.retention_deadline = past
                await session.commit()

        asyncio.run(_set_deadline())
        user_b, org_b = _build_org_b_user()

        async def _evaluate():
            async with _session_cm() as session:
                svc = RetentionService(session)
                return await svc.evaluate_retention_deadlines(
                    organization_id=org_b
                )

        eligible = asyncio.run(_evaluate())
        assert len(eligible) == 0

    def test_physically_delete_stored_objects(self):
        """After physical deletion, StoredObject rows are gone."""
        user_a, org_a, project_id = _build_org_project_archived()

        async def _get_object_id():
            async with _session_cm() as session:
                result = await session.execute(
                    select(StoredObject.id).join(DocumentVersion)
                    .join(TenderDocument).join(Project)
                    .where(Project.organization_id == org_a)
                )
                return result.scalar_one()

        obj_id = asyncio.run(_get_object_id())

        async def _delete():
            async with _session_cm() as session:
                svc = RetentionService(session)
                count = await svc.physically_delete_stored_objects([obj_id])
                await session.commit()
                return count

        deleted = asyncio.run(_delete())
        assert deleted == 1

        async def _verify_gone():
            async with _session_cm() as session:
                obj = await session.get(StoredObject, obj_id)
                return obj is None

        assert asyncio.run(_verify_gone()) is True


# ---------------------------------------------------------------------------
# Hard project deletion
# ---------------------------------------------------------------------------


class TestHardProjectDeletion:
    def test_hard_delete_archived_project_succeeds(self):
        """An archived project can be hard-deleted."""
        user_a, org_a, project_id = _build_org_project_archived()

        resp = client.delete(
            f"/projects/{project_id}",
            headers=_headers(user_a, org_a),
        )
        assert resp.status_code == 204

        # Verify the project is gone
        async def _check():
            async with _session_cm() as session:
                project = await session.get(Project, project_id)
                return project

        assert asyncio.run(_check()) is None

    def test_hard_delete_non_archived_project_rejected(self):
        """Non-archived projects cannot be hard-deleted (409)."""
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()

        async def _setup():
            async with _session_cm() as session:
                session.add(Organization(id=org_id, name="Org"))
                session.add(
                    User(
                        id=user_id,
                        auth_provider="dev",
                        auth_provider_user_id=str(user_id),
                    )
                )
                session.add(
                    Membership(organization_id=org_id, user_id=user_id, role="owner")
                )
                session.add(
                    Project(
                        id=project_id,
                        organization_id=org_id,
                        name="Draft Project",
                        status=ProjectStatus.DRAFT,
                        created_by=user_id,
                    )
                )
                await session.commit()

        asyncio.run(_setup())

        resp = client.delete(
            f"/projects/{project_id}",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 409

    def test_hard_delete_cross_tenant_denied(self):
        """Org B cannot hard-delete Org A's project."""
        user_a, org_a, project_id = _build_org_project_archived()
        user_b, org_b = _build_org_b_user()

        resp = client.delete(
            f"/projects/{project_id}",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

        # Verify the project still exists
        async def _check():
            async with _session_cm() as session:
                project = await session.get(Project, project_id)
                return project is not None

        assert asyncio.run(_check()) is True

    def test_hard_delete_not_found(self):
        """Hard-deleting a non-existent project returns 404."""
        user_a, org_a, _ = _build_org_project_archived()

        resp = client.delete(
            f"/projects/{uuid.uuid4()}",
            headers=_headers(user_a, org_a),
        )
        assert resp.status_code == 404

    def test_hard_delete_requires_auth(self):
        """Hard delete without auth returns 401."""
        _, _, project_id = _build_org_project_archived()

        resp = client.delete(f"/projects/{project_id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Upload size limit config
# ---------------------------------------------------------------------------


class TestResourceLimits:
    def test_upload_max_bytes_config(self):
        """The default upload_max_bytes is 50 MB."""
        settings = get_settings()
        assert settings.upload_max_bytes == 50 * 1024 * 1024

    def test_max_pdf_pages_config(self):
        """The default max_pdf_pages is 500."""
        settings = get_settings()
        assert settings.max_pdf_pages == 500

    def test_retention_days_config(self):
        """Retention days are configured."""
        settings = get_settings()
        assert settings.retention_originals_days == 90
        assert settings.retention_rendered_days == 30
        assert settings.retention_exports_days == 30

    def test_request_timeout_config(self):
        """Request timeout is configurable."""
        settings = get_settings()
        assert settings.request_timeout_seconds == 30.0


# ---------------------------------------------------------------------------
# Audit correlation ID
# ---------------------------------------------------------------------------


class TestAuditCorrelation:
    def test_correlation_id_on_audit_log(self):
        """When a project is hard-deleted, an audit event with the
        correlation ID is recorded."""
        from tender_compliance_api.db.models import AuditLog

        user_a, org_a, project_id = _build_org_project_archived()

        resp = client.delete(
            f"/projects/{project_id}",
            headers={
                "x-dev-user-id": str(user_a),
                "x-dev-organization-id": str(org_a),
                "x-correlation-id": "delete-trace-001",
            },
        )
        assert resp.status_code == 204
        trace_id = resp.headers.get("x-correlation-id", "")

        async def _check_audit():
            async with _session_cm() as session:
                # Filter by this specific project's org so we don't pick
                # up audit logs from other tests sharing the session DB.
                result = await session.execute(
                    select(AuditLog)
                    .where(AuditLog.action == "project.hard_delete")
                    .where(AuditLog.organization_id == org_a)
                    .where(AuditLog.entity_id == project_id)
                    .order_by(AuditLog.created_at.desc())
                )
                audit = result.scalars().first()
                return audit

        audit = asyncio.run(_check_audit())
        assert audit is not None
        assert audit.correlation_id == trace_id
