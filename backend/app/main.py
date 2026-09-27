from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    accountability,
    ai,
    auth,
    executions,
    forms,
    organizations,
    periodic,
    projects,
    reports,
    templates,
    tor,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/docs",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api/v1")
api.include_router(auth.router)
api.include_router(organizations.router)
api.include_router(projects.router)
api.include_router(ai.router)
api.include_router(tor.router)
api.include_router(executions.router)
api.include_router(reports.router)
api.include_router(accountability.router)
api.include_router(periodic.router)
api.include_router(templates.router)
api.include_router(forms.router)
app.include_router(api)


@app.get("/health", tags=["système"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
