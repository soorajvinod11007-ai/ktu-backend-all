# admin/schemas
"""Pydantic schemas for the admin CRUD dashboard.

Read schemas expose the raw FK ids *and* the human-readable labels that the
frontend table needs. The labels are produced by each resource's
``row_mapper`` (see ``app/modules/admin/resources/``), never by lazy
relationship access at serialization time. ``hashed_password`` appears in
no schema, anywhere.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.models import UserRole
from app.modules.students.models import StudentStatus


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #
class AdminReadBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


# --------------------------------------------------------------------------- #
# users
# --------------------------------------------------------------------------- #
class UserRead(AdminReadBase):
    username: str
    email: str
    full_name: str | None = None
    role: UserRole
    is_active: bool


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=3, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole = UserRole.ADMIN
    is_active: bool = True
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=3, max_length=64)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


# --------------------------------------------------------------------------- #
# programs
# --------------------------------------------------------------------------- #
class ProgramRead(AdminReadBase):
    code: str
    name: str
    is_active: bool


class ProgramCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=4)
    name: str = Field(min_length=1, max_length=255)
    is_active: bool = True


class ProgramUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, min_length=1, max_length=4)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


# --------------------------------------------------------------------------- #
# batches
# --------------------------------------------------------------------------- #
class BatchRead(AdminReadBase):
    start_year: int
    end_year: int
    label: str


class BatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_year: int = Field(ge=1900, le=2200)
    end_year: int = Field(ge=1901, le=2201)
    label: str = Field(min_length=1, max_length=16)


class BatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_year: int | None = Field(default=None, ge=1900, le=2200)
    end_year: int | None = Field(default=None, ge=1901, le=2201)
    label: str | None = Field(default=None, min_length=1, max_length=16)


# --------------------------------------------------------------------------- #
# divisions
# --------------------------------------------------------------------------- #
class DivisionRead(AdminReadBase):
    program_id: uuid.UUID
    batch_id: uuid.UUID
    name: str
    program_code: str | None = None
    batch_label: str | None = None


class DivisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: uuid.UUID
    batch_id: uuid.UUID
    name: str = Field(min_length=1, max_length=16)


class DivisionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=16)


# --------------------------------------------------------------------------- #
# students
# --------------------------------------------------------------------------- #
class StudentRead(AdminReadBase):
    register_no: str
    name: str
    program_id: uuid.UUID
    batch_id: uuid.UUID
    division_id: uuid.UUID | None = None
    status: StudentStatus
    is_flagged: bool
    # Readable labels — populated by the row_mapper.
    program_code: str | None = None
    program_name: str | None = None
    batch_label: str | None = None
    division_name: str | None = None


class StudentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    register_no: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=255)
    # Both optional: the register-number parser fills them when omitted.
    program_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    division_id: uuid.UUID | None = None
    status: StudentStatus = StudentStatus.ACTIVE
    # Rarely set by the client; the hook computes it from the register_no.
    is_flagged: bool | None = None


class StudentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    register_no: str | None = Field(default=None, min_length=1, max_length=16)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    program_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    division_id: uuid.UUID | None = None
    status: StudentStatus | None = None
    is_flagged: bool | None = None


# --------------------------------------------------------------------------- #
# faculty
# --------------------------------------------------------------------------- #
class FacultyRead(AdminReadBase):
    name: str
    email: str
    ktu_id: str | None = None
    department_id: uuid.UUID | None = None
    is_active: bool
    program_code: str | None = None


class FacultyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    ktu_id: str | None = Field(default=None, max_length=32)
    department_id: uuid.UUID | None = None
    is_active: bool = True


class FacultyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    ktu_id: str | None = Field(default=None, max_length=32)
    department_id: uuid.UUID | None = None
    is_active: bool | None = None


# --------------------------------------------------------------------------- #
# subjects
# --------------------------------------------------------------------------- #
class SubjectRead(AdminReadBase):
    code: str
    name: str
    semester: int
    scheme: str
    type: str


class SubjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    semester: int = Field(ge=1, le=12)
    scheme: str = Field(min_length=1, max_length=32)
    type: str = Field(min_length=1, max_length=32)


class SubjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    semester: int | None = Field(default=None, ge=1, le=12)
    scheme: str | None = Field(default=None, min_length=1, max_length=32)
    type: str | None = Field(default=None, min_length=1, max_length=32)


# --------------------------------------------------------------------------- #
# course-offerings
# --------------------------------------------------------------------------- #
class CourseOfferingRead(AdminReadBase):
    program_id: uuid.UUID
    batch_id: uuid.UUID
    division_id: uuid.UUID | None = None
    subject_id: uuid.UUID
    faculty_id: uuid.UUID | None = None
    semester: int
    academic_year: str
    subject_code: str | None = None
    subject_name: str | None = None
    faculty_name: str | None = None
    program_code: str | None = None
    batch_label: str | None = None
    division_name: str | None = None


class CourseOfferingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: uuid.UUID
    batch_id: uuid.UUID
    division_id: uuid.UUID | None = None
    subject_id: uuid.UUID
    faculty_id: uuid.UUID | None = None
    semester: int = Field(ge=1, le=12)
    academic_year: str = Field(min_length=4, max_length=16)


class CourseOfferingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    division_id: uuid.UUID | None = None
    subject_id: uuid.UUID | None = None
    faculty_id: uuid.UUID | None = None
    semester: int | None = Field(default=None, ge=1, le=12)
    academic_year: str | None = Field(default=None, min_length=4, max_length=16)


# --------------------------------------------------------------------------- #
# exam-sessions
# --------------------------------------------------------------------------- #
class ExamSessionRead(AdminReadBase):
    name: str
    exam_type: str


class ExamSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    exam_type: str = Field(min_length=1, max_length=32)


class ExamSessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    exam_type: str | None = Field(default=None, min_length=1, max_length=32)


# --------------------------------------------------------------------------- #
# results (semester_results)
# --------------------------------------------------------------------------- #
class ResultRead(AdminReadBase):
    student_id: uuid.UUID
    subject_id: uuid.UUID
    exam_session_id: uuid.UUID
    semester: int
    grade: str | None = None
    status: str
    student_name: str | None = None
    register_no: str | None = None
    subject_code: str | None = None
    subject_name: str | None = None
    exam_type: str | None = None


class ResultCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: uuid.UUID
    subject_id: uuid.UUID
    exam_session_id: uuid.UUID
    semester: int = Field(ge=1, le=12)
    grade: str | None = Field(default=None, max_length=4)
    status: str = Field(min_length=1, max_length=16)


class ResultUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: str | None = Field(default=None, max_length=4)
    status: str | None = Field(default=None, min_length=1, max_length=16)
    semester: int | None = Field(default=None, ge=1, le=12)


# --------------------------------------------------------------------------- #
# grade-cards
# --------------------------------------------------------------------------- #
class GradeCardRead(AdminReadBase):
    student_id: uuid.UUID
    semester: int
    exam_session_id: uuid.UUID
    student_name: str | None = None
    register_no: str | None = None
    exam_type: str | None = None


class GradeCardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: uuid.UUID
    semester: int = Field(ge=1, le=12)
    exam_session_id: uuid.UUID


class GradeCardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: uuid.UUID | None = None
    semester: int | None = Field(default=None, ge=1, le=12)
    exam_session_id: uuid.UUID | None = None


# --------------------------------------------------------------------------- #
# result-history (read-only)
# --------------------------------------------------------------------------- #
class ResultHistoryRead(AdminReadBase):
    semester_result_id: uuid.UUID
    change_type: str
    changed_by_user_id: uuid.UUID | None = None
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    register_no: str | None = None
    student_name: str | None = None


# --------------------------------------------------------------------------- #
# upload-logs (read-only)
# --------------------------------------------------------------------------- #
class UploadLogRead(AdminReadBase):
    file_type: str | None = None
    status: str | None = None
    filename: str | None = None
    resource: str | None = None
    uploaded_by_user_id: uuid.UUID | None = None
    uploaded_by_username: str | None = None
    total_rows: int | None = None
    valid_rows: int | None = None
    error_rows: int | None = None


__all__ = [
    "AdminReadBase",
    # users
    "UserRead", "UserCreate", "UserUpdate",
    # programs
    "ProgramRead", "ProgramCreate", "ProgramUpdate",
    # batches
    "BatchRead", "BatchCreate", "BatchUpdate",
    # divisions
    "DivisionRead", "DivisionCreate", "DivisionUpdate",
    # students
    "StudentRead", "StudentCreate", "StudentUpdate",
    # faculty
    "FacultyRead", "FacultyCreate", "FacultyUpdate",
    # subjects
    "SubjectRead", "SubjectCreate", "SubjectUpdate",
    # course-offerings
    "CourseOfferingRead", "CourseOfferingCreate", "CourseOfferingUpdate",
    # exam-sessions
    "ExamSessionRead", "ExamSessionCreate", "ExamSessionUpdate",
    # results
    "ResultRead", "ResultCreate", "ResultUpdate",
    # grade-cards
    "GradeCardRead", "GradeCardCreate", "GradeCardUpdate",
    # read-only
    "ResultHistoryRead", "UploadLogRead",
]