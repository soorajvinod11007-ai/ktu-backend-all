"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware
from app.core.audit_middleware import AuditContextMiddleware


from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.faculty.router import router as faculty_router
from app.modules.reports.router import router as reports_router
from app.modules.results.router import router as results_router
from app.modules.students.router import router as students_router
from app.modules.subjects.router import router as subjects_router
from app.modules.uploads.router import router as uploads_router

settings = get_settings()
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("startup", extra={"environment": settings.ENVIRONMENT})
    yield
    logger.info("shutdown")


app = FastAPI(
    title="College Result Analysis System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestIDMiddleware)

app.add_middleware(AuditContextMiddleware)

register_exception_handlers(app)

api_v1 = APIRouter(prefix="/api/v1")


@api_v1.get("/health", tags=["health"], summary="Health check")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "environment": settings.ENVIRONMENT}


api_v1.include_router(auth_router)
api_v1.include_router(students_router)
api_v1.include_router(faculty_router)
api_v1.include_router(subjects_router)
api_v1.include_router(results_router)
api_v1.include_router(uploads_router)
api_v1.include_router(reports_router)
api_v1.include_router(admin_router)

app.include_router(api_v1)
