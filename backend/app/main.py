"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.models import Base
from app.routers import (
    analytics,
    machines,
    maintenance,
    production,
    sensors,
    sites,
    tenants,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DESCRIPTION = """
Multi-tenant manufacturing AI platform with **maturity-driven analytics**.

Every tenant is assessed across four data dimensions (CMMS, production, IoT
and data quality) and placed on a 0-4 maturity level. Features unlock as the
customer's data matures, so the product grows with the plant rather than
demanding a full IoT rollout on day one.

**Tenant scope** - all resource endpoints require an `X-Tenant-ID` header
carrying the tenant's id or slug. Every query is filtered on it.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup when running against a fresh database."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema verified")
    except Exception:  # pragma: no cover - startup diagnostics
        logger.exception("Could not verify database schema")
    yield


app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Surface domain validation errors as 400 rather than 500."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)}
    )


@app.get("/health", tags=["system"])
def health() -> dict:
    """Liveness and database connectivity probe."""
    db_ok = True
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - only hit when the DB is down
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unavailable",
        "environment": settings.environment,
        "version": app.version,
    }


@app.get("/", tags=["system"])
def root() -> dict:
    """Service banner pointing at the interactive docs."""
    return {
        "service": settings.app_name,
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
    }


for module in (tenants, machines, maintenance, production, analytics, sensors, sites):
    app.include_router(module.router, prefix=settings.api_v1_prefix)
