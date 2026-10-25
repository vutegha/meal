import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import (
    accountability,
    admin,
    ai,
    auth,
    billing,
    dashboard,
    executions,
    forms,
    organizations,
    periodic,
    personal_data,
    projects,
    reports,
    sms,
    templates,
    tor,
)
from app.core.config import get_settings
from app.core.db import SessionLocal, check_role
from app.services import ratelimit
from app.services.jobs import QueueUnavailable

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await check_role()
    yield


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    version="0.1.0",
    # Documentation interactive fermée en production : elle décrit toute la surface de l'API.
    openapi_url=None if settings.is_production else "/api/v1/openapi.json",
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(QueueUnavailable)
async def queue_unavailable(_: Request, exc: QueueUnavailable) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


api = APIRouter(prefix="/api/v1")
api.include_router(auth.router)
api.include_router(billing.router)
api.include_router(organizations.router)
api.include_router(dashboard.router)
api.include_router(projects.router)
api.include_router(ai.router)
api.include_router(tor.router)
api.include_router(executions.router)
api.include_router(reports.router)
api.include_router(accountability.router)
api.include_router(periodic.router)
api.include_router(templates.router)
api.include_router(forms.router)
api.include_router(sms.router)
api.include_router(admin.router)
api.include_router(personal_data.router)
app.include_router(api)


@app.get("/health", tags=["système"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["système"])
async def ready(response: Response) -> dict[str, str]:
    """Base et Redis joignables : pour la surveillance et le contrôle de santé de Docker."""
    checks = {"database": "ok", "redis": "ok"}
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - toute panne de la base rend le service indisponible
        logger.exception("Base de données injoignable")
        checks["database"] = "error"
    if settings.login_rate_limit_storage != "memory":
        try:
            await ratelimit.ping()
        except Exception:  # noqa: BLE001
            logger.exception("Redis injoignable")
            checks["redis"] = "error"
    else:
        checks["redis"] = "skipped"
    if "error" in checks.values():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return checks
