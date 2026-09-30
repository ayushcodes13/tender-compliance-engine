from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from tender_compliance_api.config import get_settings
from tender_compliance_api.db.session import close_engine, init_engine
from tender_compliance_api.routes.health import router as health_router
from tender_compliance_api.routes.projects import router as projects_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Application lifecycle: initialize the database engine on startup,
    and dispose of it on shutdown."""
    database_url = get_settings().database_url
    if database_url:
        init_engine(database_url)
    yield
    await close_engine()


app = FastAPI(
    title="Tender Compliance Engine API",
    version="0.1.0",
    description="Evidence-first technical tender compliance API.",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(projects_router)
