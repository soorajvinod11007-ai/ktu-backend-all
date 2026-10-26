"""Repository layer for upload logs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.uploads.models import UploadFileType, UploadLog, UploadStatus


class UploadRepository:
    @staticmethod
    def create_log(
        db: Session,
        *,
        file_name: str,
        file_type: str | UploadFileType,
        uploaded_by: uuid.UUID | None,
        status: UploadStatus = UploadStatus.PREVIEW,
        rows_parsed: int = 0,
        rows_failed: int = 0,
        preview_payload: dict[str, Any] | None = None,
        error_summary: list[dict[str, Any]] | None = None,
        file_hash: str | None = None,
        stored_path: str | None = None,
        exam_session_id: uuid.UUID | None = None,
    ) -> UploadLog:
        if isinstance(file_type, str):
            file_type = UploadFileType(file_type)

        log = UploadLog(
            file_name=file_name,
            file_type=file_type,
            uploaded_by=uploaded_by,
            status=status,
            rows_parsed=rows_parsed,
            rows_failed=rows_failed,
            preview_payload=preview_payload,
            error_summary=error_summary,
            file_hash=file_hash,
            stored_path=stored_path,
            exam_session_id=exam_session_id,
        )
        db.add(log)
        db.flush()
        return log

    @staticmethod
    def get_by_id(
        db: Session, upload_id: uuid.UUID, include_deleted: bool = False
    ) -> UploadLog | None:
        stmt = select(UploadLog).where(UploadLog.id == upload_id)
        if not include_deleted:
            stmt = stmt.where(UploadLog.deleted_at.is_(None))
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_by_hash(db: Session, file_hash: str) -> UploadLog | None:
        stmt = (
            select(UploadLog)
            .where(
                UploadLog.file_hash == file_hash,
                UploadLog.deleted_at.is_(None),
                UploadLog.status != UploadStatus.CANCELLED,
            )
            .order_by(UploadLog.created_at.desc())
        )
        return db.execute(stmt).scalars().first()

    @staticmethod
    def list_logs(
        db: Session,
        *,
        page: int = 1,
        page_size: int = 25,
        file_type: str | None = None,
        status: str | None = None,
    ) -> tuple[list[UploadLog], int]:
        stmt = select(UploadLog).where(UploadLog.deleted_at.is_(None))

        if file_type:
            stmt = stmt.where(UploadLog.file_type == UploadFileType(file_type))
        if status:
            stmt = stmt.where(UploadLog.status == UploadStatus(status))

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = int(db.execute(total_stmt).scalar_one())

        offset = max(0, (page - 1) * page_size)
        items_stmt = stmt.order_by(UploadLog.created_at.desc()).offset(offset).limit(page_size)
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    @staticmethod
    def soft_delete(db: Session, log: UploadLog) -> None:
        log.deleted_at = datetime.now(UTC)
        log.status = UploadStatus.CANCELLED
        db.flush()


__all__ = ["UploadRepository"]
