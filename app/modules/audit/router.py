from __future__ import annotations
import uuid
from typing import Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.modules.auth.dependencies import require_admin
from app.modules.audit.models import AuditLog

router = APIRouter(prefix="/audit-logs", tags=["admin:audit-logs"])

@router.get("")
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    resource: str | None = None,
    action: str | None = None,
    db: Session = Depends(get_db),
    _: Any = Depends(require_admin),
) -> dict:
    stmt = select(AuditLog)
    if resource:
        stmt = stmt.where(AuditLog.resource == resource)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.order_by(AuditLog.created_at.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [
            {
                "id": str(r.id),
                "user_id": str(r.user_id) if r.user_id else None,
                "action": r.action.value,
                "resource": r.resource,
                "record_id": str(r.record_id) if r.record_id else None,
                "changes": r.changes,
                "ip": r.ip,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    }

__all__ = ["router"]
