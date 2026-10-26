"""GET /admin/dashboard — counts + flagged students + recent uploads.

Readable by admin AND principal. Cached for
``ADMIN_DASHBOARD_CACHE_SECONDS`` behind a small TTL interface so the
storage can later move to Redis without changing the handler.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.common.cache import TTLCache
from app.core.config import get_settings
from app.core.database import get_db
from app.modules.auth.dependencies import require_admin_or_principal
from app.modules.faculty.models import Faculty
from app.modules.students.models import Batch, Program, Student
from app.modules.faculty.models import Subject
from app.modules.uploads.models import UploadLog  # type: ignore

try:  # results module may expose this under a different path
    from app.modules.results.models import SemesterResult  # type: ignore
except Exception:  # pragma: no cover
    SemesterResult = None  # type: ignore


_CACHE: TTLCache | None = None


def _cache() -> TTLCache:
    global _CACHE
    if _CACHE is None:
        settings = get_settings()
        ttl = int(getattr(settings, "ADMIN_DASHBOARD_CACHE_SECONDS", 60))
        _CACHE = TTLCache(ttl)
    return _CACHE


def _live_count(db: Session, model: Any) -> int:
    stmt = select(func.count()).select_from(model).where(model.deleted_at.is_(None))
    return int(db.execute(stmt).scalar_one())


def _build_payload(db: Session) -> dict[str, Any]:
    counts = {
        "students": _live_count(db, Student),
        "faculty": _live_count(db, Faculty),
        "subjects": _live_count(db, Subject),
        "results": _live_count(db, SemesterResult) if SemesterResult else 0,
        "batches": _live_count(db, Batch),
        "programs": _live_count(db, Program),
    }
    flagged = int(
        db.execute(
            select(func.count())
            .select_from(Student)
            .where(Student.deleted_at.is_(None), Student.is_flagged.is_(True))
        ).scalar_one()
    )

    recent_stmt = (
        select(UploadLog)
        .where(UploadLog.deleted_at.is_(None))
        .order_by(UploadLog.created_at.desc())
        .limit(10)
    )
    if hasattr(UploadLog, "uploaded_by_user"):
        recent_stmt = recent_stmt.options(selectinload(UploadLog.uploaded_by_user))
    recent = db.execute(recent_stmt).scalars().unique().all()

    return {
        "counts": counts,
        "flagged_students": flagged,
        "recent_uploads": [
            {
                "id": str(u.id),
                "file_type": getattr(u, "file_type", None),
                "status": getattr(u, "status", None),
                "filename": getattr(u, "filename", None),
                "resource": getattr(u, "resource", None),
                "total_rows": getattr(u, "total_rows", None),
                "valid_rows": getattr(u, "valid_rows", None),
                "error_rows": getattr(u, "error_rows", None),
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in recent
        ],
    }


def get_dashboard(
    db: Session = Depends(get_db),
    _user=Depends(require_admin_or_principal),
) -> dict[str, Any]:
    return _cache().get_or_set("dashboard", lambda: _build_payload(db))


__all__ = ["get_dashboard"]