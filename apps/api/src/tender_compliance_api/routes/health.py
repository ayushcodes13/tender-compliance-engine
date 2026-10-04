from typing import Any, Literal, TypedDict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.config import get_settings
from tender_compliance_api.db.session import get_session
from tender_compliance_api.queue import DEFAULT_QUEUE, QueueAdapter
from tender_compliance_api.routes.uploads import (
    get_queue_adapter,
    get_scanner,
    get_storage_adapter,
)
from tender_compliance_api.scan.adapter import MalwareScanner
from tender_compliance_api.storage.adapter import ObjectStorageAdapter

router = APIRouter(tags=["system"])


class HealthResponse(TypedDict):
    status: Literal["ok"]
    service: str


class ReadinessResponse(TypedDict):
    status: Literal["ready", "not_ready"]
    service: str
    components: dict[str, str]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness only: the API process is up."""
    return {"status": "ok", "service": "tender-compliance-api"}


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    queue: QueueAdapter = Depends(get_queue_adapter),  # noqa: B008
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),  # noqa: B008
    scanner: MalwareScanner = Depends(get_scanner),  # noqa: B008
) -> ReadinessResponse | JSONResponse:
    """Return whether the stack can accept and process document work.

    This is deliberately stricter than /health. It checks the durable
    dependencies required by the user journey: database, queue, object storage,
    and the AI credential in production. It never logs or returns secrets.
    """
    settings = get_settings()
    components: dict[str, str] = {}
    failures: list[str] = []

    try:
        await session.execute(text("SELECT 1"))
        components["database"] = "ready"
    except Exception:
        components["database"] = "unavailable"
        failures.append("database")

    try:
        await queue.size(DEFAULT_QUEUE)
        components["queue"] = "ready"
    except Exception:
        components["queue"] = "unavailable"
        failures.append("queue")
    finally:
        await queue.close()

    try:
        await storage.ready()
        components["object_storage"] = "ready"
    except Exception:
        components["object_storage"] = "unavailable"
        failures.append("object_storage")

    try:
        if await scanner.ready():
            components["malware_scanner"] = "ready"
        else:
            components["malware_scanner"] = "unavailable"
            failures.append("malware_scanner")
    except Exception:
        components["malware_scanner"] = "unavailable"
        failures.append("malware_scanner")

    if settings.app_env == "production":
        if settings.openai_api_key.strip():
            components["ai_provider"] = "configured"
        else:
            components["ai_provider"] = "missing_api_key"
            failures.append("ai_provider")
    else:
        components["ai_provider"] = "development"

    payload: ReadinessResponse = {
        "status": "not_ready" if failures else "ready",
        "service": "tender-compliance-api",
        "components": components,
    }
    if failures:
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/metrics")
def get_metrics_endpoint() -> dict[str, Any]:
    """Return a point-in-time snapshot of in-memory metrics (CP46).

    No external metrics backend is required for Phase 1. The registry
    can be scraped by Prometheus later by wrapping this endpoint.
    """
    from tender_compliance_api.metrics import get_metrics

    return get_metrics().snapshot()
