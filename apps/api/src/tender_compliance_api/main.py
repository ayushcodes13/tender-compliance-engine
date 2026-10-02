from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request

from tender_compliance_api.config import get_settings
from tender_compliance_api.db.session import close_engine, init_engine
from tender_compliance_api.logs import get_logger, log_event, set_correlation_id
from tender_compliance_api.routes.compliance import (
    router as compliance_router,
)
from tender_compliance_api.routes.conflicts import (
    router as conflicts_router,
)
from tender_compliance_api.routes.evidence import router as evidence_router
from tender_compliance_api.routes.health import router as health_router
from tender_compliance_api.routes.oem_documents import router as oem_documents_router
from tender_compliance_api.routes.projects import router as projects_router
from tender_compliance_api.routes.reasoning import router as reasoning_router
from tender_compliance_api.routes.requirements import router as requirements_router
from tender_compliance_api.routes.source_viewer import router as source_viewer_router
from tender_compliance_api.routes.uploads import router as uploads_router
from tender_compliance_api.routes.vendor_specs import (
    router as vendor_specs_router,
)

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Application lifecycle: initialize the database engine on startup,
    and dispose of it on shutdown."""
    from tender_compliance_api.storage.fake import FakeStorageAdapter

    database_url = get_settings().database_url
    if database_url:
        init_engine(database_url)
    # Attach a default storage adapter to app state for the hard-delete
    # route; overrides in tests replace this.
    if not hasattr(app.state, "storage_adapter"):
        app.state.storage_adapter = FakeStorageAdapter()
    yield
    await close_engine()


async def correlation_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Any]],
) -> Any:
    """Inject a per-request correlation ID into the logging context.

    The ID is also available to route handlers via ``request.state`` and
    ``get_correlation_id()`` so audit events can reference it.
    """
    cid = request.headers.get("x-correlation-id")
    cid = set_correlation_id(cid)
    request.state.correlation_id = cid

    log_event(
        logger,
        level=20,
        message="request_started",
        correlation_id=cid,
        method=request.method,
        path=str(request.url.path),
    )
    response = await call_next(request)
    response.headers["x-correlation-id"] = cid
    return response


app = FastAPI(
    title="Tender Compliance Engine API",
    version="0.1.0",
    description="Evidence-first technical tender compliance API.",
    lifespan=lifespan,
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
app.include_router(reasoning_router)
