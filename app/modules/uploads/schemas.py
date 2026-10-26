"""Pydantic v2 schemas for upload endpoints and logs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.uploads.models import UploadFileType, UploadStatus


class UploadSummary(BaseModel):
    rows_total: int = 0
    rows_ok: int = 0
    rows_with_errors: int = 0
    new: int = 0
    updates: int = 0


class UploadErrorItem(BaseModel):
    page: int | None = None
    row: int | None = None
    code: str
    message: str


class UploadPreviewResponse(BaseModel):
    upload_id: uuid.UUID
    file_type: str
    summary: UploadSummary
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[UploadErrorItem] = Field(default_factory=list)
    warning: str | None = None


class UploadConfirmResponse(BaseModel):
    upload_id: uuid.UUID
    status: str
    rows_applied: int
    summary: dict[str, Any] | None = None


class UploadCancelResponse(BaseModel):
    upload_id: uuid.UUID
    status: str = "cancelled"


class UploadLogBase(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    file_type: UploadFileType
    uploaded_by: uuid.UUID | None = None
    rows_parsed: int = Field(default=0, ge=0)
    rows_failed: int = Field(default=0, ge=0)
    status: UploadStatus = UploadStatus.PENDING
    error_summary: list[dict[str, Any]] | dict[str, Any] | None = None


class UploadLogCreate(UploadLogBase):
    pass


class UploadLogUpdate(BaseModel):
    rows_parsed: int | None = Field(default=None, ge=0)
    rows_failed: int | None = Field(default=None, ge=0)
    status: UploadStatus | None = None
    error_summary: list[dict[str, Any]] | dict[str, Any] | None = None


class UploadLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    file_name: str
    file_type: str
    uploaded_by: uuid.UUID | None = None
    rows_parsed: int
    rows_failed: int
    status: str
    created_at: datetime
    updated_at: datetime


class UploadListResponse(BaseModel):
    items: list[UploadLogRead]
    total: int
    page: int
    page_size: int


__all__ = [
    "UploadSummary",
    "UploadErrorItem",
    "UploadPreviewResponse",
    "UploadConfirmResponse",
    "UploadCancelResponse",
    "UploadLogBase",
    "UploadLogCreate",
    "UploadLogUpdate",
    "UploadLogRead",
    "UploadListResponse",
]
