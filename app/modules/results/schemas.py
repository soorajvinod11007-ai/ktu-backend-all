# results/schemas
"""Pydantic v2 schemas for exam sessions, semester results, result history, grade cards."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.results.models import (
    ChangeType,
    ExamType,
    Grade,
    ResultStatus,
)


# --------------------------------------------------------------------------- #
# ExamSession
# --------------------------------------------------------------------------- #
class ExamSessionBase(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    exam_type: ExamType = ExamType.REGULAR
    scheme: str = Field(min_length=1, max_length=8)
    published_on: date | None = None


class ExamSessionCreate(ExamSessionBase):
    pass


class ExamSessionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=32)
    exam_type: ExamType | None = None
    scheme: str | None = Field(default=None, min_length=1, max_length=8)
    published_on: date | None = None


class ExamSessionRead(ExamSessionBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# SemesterResult
# --------------------------------------------------------------------------- #
class SemesterResultBase(BaseModel):
    student_id: uuid.UUID
    subject_id: uuid.UUID
    exam_session_id: uuid.UUID
    semester: int = Field(ge=1, le=8)
    grade: Grade | None = None
    status: ResultStatus
    is_regular_attempt: bool = True


class SemesterResultCreate(SemesterResultBase):
    pass


class SemesterResultUpdate(BaseModel):
    semester: int | None = Field(default=None, ge=1, le=8)
    grade: Grade | None = None
    status: ResultStatus | None = None
    is_regular_attempt: bool | None = None


class SemesterResultRead(SemesterResultBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# ResultHistory
# --------------------------------------------------------------------------- #
class ResultHistoryBase(BaseModel):
    semester_result_id: uuid.UUID
    old_grade: Grade | None = None
    new_grade: Grade | None = None
    old_status: ResultStatus | None = None
    new_status: ResultStatus | None = None
    change_type: ChangeType
    source_upload_id: uuid.UUID | None = None


class ResultHistoryCreate(ResultHistoryBase):
    pass


class ResultHistoryUpdate(BaseModel):
    # History is append-only in normal operation; Update exists for admin corrections.
    old_grade: Grade | None = None
    new_grade: Grade | None = None
    old_status: ResultStatus | None = None
    new_status: ResultStatus | None = None
    change_type: ChangeType | None = None
    source_upload_id: uuid.UUID | None = None


class ResultHistoryRead(ResultHistoryBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# GradeCard
# --------------------------------------------------------------------------- #
class GradeCardBase(BaseModel):
    student_id: uuid.UUID
    semester: int = Field(ge=1, le=8)
    exam_session_id: uuid.UUID
    earned_credits: int | None = Field(default=None, ge=0)
    cumulative_credits: int | None = Field(default=None, ge=0)
    sgpa: float | None = Field(default=None, ge=0, le=10)
    cgpa: float | None = Field(default=None, ge=0, le=10)


class GradeCardCreate(GradeCardBase):
    pass


class GradeCardUpdate(BaseModel):
    earned_credits: int | None = Field(default=None, ge=0)
    cumulative_credits: int | None = Field(default=None, ge=0)
    sgpa: float | None = Field(default=None, ge=0, le=10)
    cgpa: float | None = Field(default=None, ge=0, le=10)


class GradeCardRead(GradeCardBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


__all__ = [
    "ExamSessionBase", "ExamSessionCreate", "ExamSessionUpdate", "ExamSessionRead",
    "SemesterResultBase", "SemesterResultCreate",
    "SemesterResultUpdate", "SemesterResultRead",
    "ResultHistoryBase", "ResultHistoryCreate",
    "ResultHistoryUpdate", "ResultHistoryRead",
    "GradeCardBase", "GradeCardCreate", "GradeCardUpdate", "GradeCardRead",
]