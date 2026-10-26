"""Uploads router: file upload preview, confirmation, deletion, and history."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_admin
from app.modules.auth.models import User
from app.modules.uploads.schemas import (
    UploadCancelResponse,
    UploadConfirmResponse,
    UploadListResponse,
    UploadPreviewResponse,
)
from app.modules.uploads.service import UploadService

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post(
    "/preview",
    response_model=UploadPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview an uploaded file (saves nothing to business tables)",
)
def preview_upload(
    file: Annotated[UploadFile, File(description="Source file (.xlsx, .csv, .pdf)")],
    file_type: Annotated[
        str,
        Form(
            description=(
                "Declared file type: student_list | course_book | "
                "grade_card | result | revaluation"
            )
        ),
    ],
    exam_session_id: Annotated[
        uuid.UUID | None, Form(description="Optional exam session ID")
    ] = None,
    allow_duplicate: Annotated[
        bool, Form(description="Allow duplicate SHA-256 upload without warning failure")
    ] = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> UploadPreviewResponse:
    res = UploadService.preview_upload(
        db=db,
        user=user,
        file=file,
        file_type_str=file_type,
        exam_session_id=exam_session_id,
        allow_duplicate=allow_duplicate,
    )
    return UploadPreviewResponse.model_validate(res)


@router.post(
    "/{upload_id}/confirm",
    response_model=UploadConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Persist previewed upload rows into the database",
)
def confirm_upload(
    upload_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> UploadConfirmResponse:
    res = UploadService.confirm_upload(db=db, user=user, upload_id=upload_id)
    return UploadConfirmResponse.model_validate(res)


@router.delete(
    "/{upload_id}",
    response_model=UploadCancelResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel / soft-delete a preview upload",
)
def cancel_upload(
    upload_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> UploadCancelResponse:
    res = UploadService.cancel_upload(db=db, user=user, upload_id=upload_id)
    return UploadCancelResponse.model_validate(res)


@router.get(
    "",
    response_model=UploadListResponse,
    status_code=status.HTTP_200_OK,
    summary="List upload history",
)
def list_uploads(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    file_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> UploadListResponse:
    res = UploadService.list_uploads(
        db=db,
        user=user,
        page=page,
        page_size=page_size,
        file_type=file_type,
        status=status,
    )
    return UploadListResponse.model_validate(res)


__all__ = ["router"]
