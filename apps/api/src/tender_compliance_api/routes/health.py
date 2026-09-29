from typing import Literal, TypedDict

from fastapi import APIRouter

router = APIRouter(tags=["system"])


class HealthResponse(TypedDict):
    status: Literal["ok"]
    service: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return {"status": "ok", "service": "tender-compliance-api"}
