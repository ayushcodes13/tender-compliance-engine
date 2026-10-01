from typing import Any, Literal, TypedDict

from fastapi import APIRouter

router = APIRouter(tags=["system"])


class HealthResponse(TypedDict):
    status: Literal["ok"]
    service: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return {"status": "ok", "service": "tender-compliance-api"}


@router.get("/metrics")
def get_metrics_endpoint() -> dict[str, Any]:
    """Return a point-in-time snapshot of in-memory metrics (CP46).

    No external metrics backend is required for Phase 1.  The registry
    can be scraped by Prometheus later by wrapping this endpoint.
    """
    from tender_compliance_api.metrics import get_metrics

    return get_metrics().snapshot()
