"""Assembles the /api/v1/admin router.

Ordering note: /dashboard and /options are declared first so their
literal segments win over any resource-router path. Each resource router
then owns its own literal prefix (/users, /programs, ...), which is why
they cannot shadow each other.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.crud_router import build_resource_router
from app.core.database import get_db
from app.modules.admin.dashboard import get_dashboard
from app.modules.admin.options import list_options
from app.modules.admin.registry import RESOURCE_CONFIGS
from app.modules.auth.dependencies import require_admin

# add after the options route, before the per-resource loop:
from app.modules.audit.router import router as audit_router  # noqa: E402


router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(audit_router)
# --------------------------------------------------------------------------- #
# Dashboard — admin AND principal
# --------------------------------------------------------------------------- #
@router.get(
    "/dashboard",
    summary="Admin dashboard counts (admin or principal)",
)
def dashboard(payload: dict = Depends(get_dashboard)) -> dict:
    return payload


# --------------------------------------------------------------------------- #
# Options helper — dropdown / typeahead
# --------------------------------------------------------------------------- #
@router.get(
    "/options/{resource}",
    summary="Dropdown options for a resource",
    dependencies=[Depends(require_admin)],
)
def options(
    resource: str,
    q: str | None = Query(None, description="Typeahead query."),
    limit: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
) -> list[dict]:
    return list_options(resource=resource, db=db, q=q, limit=limit)


# --------------------------------------------------------------------------- #
# Per-resource CRUD + export + import
# --------------------------------------------------------------------------- #
for _config in RESOURCE_CONFIGS:
    router.include_router(build_resource_router(_config))


__all__ = ["router"]