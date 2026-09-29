from fastapi import FastAPI

from tender_compliance_api.routes.health import router as health_router

app = FastAPI(
    title="Tender Compliance Engine API",
    version="0.1.0",
    description="Evidence-first technical tender compliance API.",
)

app.include_router(health_router)
