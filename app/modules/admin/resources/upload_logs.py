"""upload-logs admin resource (read-only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import selectinload

from app.common.crud import ResourceConfig
from app.modules.admin.schemas import UploadLogRead
from app.modules.uploads.models import UploadLog  # type: ignore


def _row_mapper(u: UploadLog) -> dict[str, Any]:
    uploader = getattr(u, "uploaded_by_user", None)
    return {
        "id": u.id,
        "file_type": getattr(u, "file_type", None),
        "status": getattr(u, "status", None),
        "filename": getattr(u, "filename", None),
        "resource": getattr(u, "resource", None),
        "uploaded_by_user_id": getattr(u, "uploaded_by_user_id", None),
        "uploaded_by_username": getattr(uploader, "username", None) if uploader else None,
        "total_rows": getattr(u, "total_rows", None),
        "valid_rows": getattr(u, "valid_rows", None),
        "error_rows": getattr(u, "error_rows", None),
        "created_at": u.created_at,
        "updated_at": u.updated_at,
        "deleted_at": u.deleted_at,
    }


def _load_options():
    if hasattr(UploadLog, "uploaded_by_user"):
        return (selectinload(UploadLog.uploaded_by_user),)
    return ()


CONFIG = ResourceConfig(
    name="upload-logs",
    model=UploadLog,
    read_schema=UploadLogRead,
    filter_fields={
        "file_type": getattr(UploadLog, "file_type", None),
        "status": getattr(UploadLog, "status", None),
    },
    sortable_fields={
        "created_at": UploadLog.created_at,
    },
    load_options=_load_options(),
    row_mapper=_row_mapper,
    read_only=True,
)