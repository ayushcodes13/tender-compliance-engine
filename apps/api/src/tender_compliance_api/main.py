from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from tender_compliance_api.config import get_settings
from tender_compliance_api.db.session import close_engine, init_engine
from tender_compliance_api.logs import get_logger, log_event, set_correlation_id
from tender_compliance_api.routes.compliance import router as compliance_router
from tender_compliance_api.routes.conflicts import router as conflicts_router
from tender_compliance_api.routes.evidence import router as evidence_router
from tender_compliance_api.routes.health import router as health_router
from tender_compliance_api.routes.missing_evidence import router as missing_evidence_router
from tender_compliance_api.routes.oem_documents import router as oem_documents_router
from tender_compliance_api.routes.projects import router as projects_router
from tender_compliance_api.routes.reasoning import router as reasoning_router
from tender_compliance_api.routes.requirements import router as requirements_router
from tender_compliance_api.routes.source_viewer import router as source_viewer_router
from tender_compliance_api.routes.submissions import router as submissions_router
from tender_compliance_api.routes.uploads import router as uploads_router
from tender_compliance_api.routes.vendor_specs import router as vendor_specs_router
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.s3 import S3StorageAdapter

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Initialize durable dependencies and dispose them on shutdown."""
    settings = get_settings()
    if settings.database_url:
        init_engine(settings.database_url)

    if settings.object_storage_endpoint:
        storage = S3StorageAdapter(
            endpoint_url=settings.object_storage_endpoint,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
            bucket=settings.object_storage_bucket,
            region=settings.object_storage_region,
        )
        await storage.ensure_bucket()
        app.state.storage_adapter = storage
    elif not hasattr(app.state, "storage_adapter"):
        app.state.storage_adapter = FakeStorageAdapter()

    yield
    await close_engine()


async def correlation_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Any]],
) -> Any:
    """Attach a correlation ID and emit one duration-aware request record."""
    cid = set_correlation_id(request.headers.get("x-correlation-id"))
    request.state.correlation_id = cid
    started = time.monotonic()
    status_code = 500

    log_event(
        logger,
        level=20,
        message="request_started",
        correlation_id=cid,
        method=request.method,
        path=str(request.url.path),
    )
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["x-correlation-id"] = cid
        return response
    finally:
        log_event(
            logger,
            level=20 if status_code < 500 else 40,
            message="request_finished",
            correlation_id=cid,
            method=request.method,
            path=str(request.url.path),
            status_code=status_code,
            duration_ms=int((time.monotonic() - started) * 1000),
        )


settings = get_settings()
app = FastAPI(
    title="Tender Compliance Engine API",
    version="1.0.0",
    description="Evidence-first technical tender compliance API.",
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-correlation-id"],
    )

app.middleware("http")(correlation_id_middleware)

app.include_router(health_router)
app.include_router(projects_router)
app.include_router(uploads_router)
app.include_router(oem_documents_router)
app.include_router(evidence_router)
app.include_router(requirements_router)
app.include_router(source_viewer_router)
app.include_router(vendor_specs_router)
app.include_router(compliance_router)
app.include_router(conflicts_router)
app.include_router(missing_evidence_router)
app.include_router(reasoning_router)
app.include_router(submissions_router)
