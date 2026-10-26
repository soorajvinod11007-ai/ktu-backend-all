"""Reports router.

Role policy for the whole project:
  - read endpoints  → admin + principal
  - write endpoints → admin only

The two handlers below are placeholder probes that prove the gating works.
Phase 4 replaces their bodies with real report queries; the dependency
wiring stays unchanged.
"""

from fastapi import APIRouter, Depends, status

from app.modules.auth.dependencies import (
    require_admin,
    require_admin_or_principal,
)
from app.modules.auth.models import User

router = APIRouter(prefix="/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# READ — admin AND principal can hit this
# ---------------------------------------------------------------------------
@router.get(
    "",
    summary="[placeholder] List reports. Allowed for admin + principal.",
)
def list_reports(
    user: User = Depends(require_admin_or_principal),
) -> dict[str, str]:
    # `user` is guaranteed to be an active admin or principal.
    return {"status": "ok", "viewer": user.username, "scope": "read"}


# ---------------------------------------------------------------------------
# WRITE — admin only
# ---------------------------------------------------------------------------
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="[placeholder] Create a report. Allowed for admin only.",
)
def create_report(
    user: User = Depends(require_admin),
) -> dict[str, str]:
    # `user` is guaranteed to be an active admin.
    return {"status": "created", "author": user.username, "scope": "write"}


__all__ = ["router"]