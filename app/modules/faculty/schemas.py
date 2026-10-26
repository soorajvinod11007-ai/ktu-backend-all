# faculty/schemas
"""Pydantic v2 schemas for faculty, subjects, course offerings."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.faculty.models import SubjectType


# --------------------------------------------------------------------------- #
# Faculty
# --------------------------------------------------------------------------- #
class FacultyBase(BaseModel):
    ktu_id: str | None = Field(default=None, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    department_id: uuid.UUID | None = None
    is_active: bool = True


class FacultyCreate(FacultyBase):
    pass


class FacultyUpdate(BaseModel):
    ktu_id: str | None = Field(default=None, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    department_id: uuid.UUID | None = None
    is_active: bool | None = None


class FacultyRead(FacultyBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Subject
# --------------------------------------------------------------------------- #
class SubjectBase(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=255)
    credits: int | None = Field(default=None, ge=0, le=20)
    semester: int = Field(ge=1, le=8)
    scheme: str = Field(min_length=1, max_length=8)
    type: SubjectType = SubjectType.THEORY


class SubjectCreate(SubjectBase):
    pass


class SubjectUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=16)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    credits: int | None = Field(default=None, ge=0, le=20)
    semester: int | None = Field(default=None, ge=1, le=8)
    scheme: str | None = Field(default=None, min_length=1, max_length=8)
    type: SubjectType | None = None


class SubjectRead(SubjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# CourseOffering
# --------------------------------------------------------------------------- #
class CourseOfferingBase(BaseModel):
    subject_id: uuid.UUID
    faculty_id: uuid.UUID
    batch_id: uuid.UUID
    division_id: uuid.UUID | None = None
    program_id: uuid.UUID
    semester: int = Field(ge=1, le=8)
    academic_year: str = Field(min_length=4, max_length=8)
    slot: str = Field(min_length=1, max_length=8)
    part_label: str | None = Field(default=None, max_length=16)
    is_main_faculty: bool = True


class CourseOfferingCreate(CourseOfferingBase):
    pass


class CourseOfferingUpdate(BaseModel):
    subject_id: uuid.UUID | None = None
    faculty_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    division_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    semester: int | None = Field(default=None, ge=1, le=8)
    academic_year: str | None = Field(default=None, min_length=4, max_length=8)
    slot: str | None = Field(default=None, min_length=1, max_length=8)
    part_label: str | None = Field(default=None, max_length=16)
    is_main_faculty: bool | None = None


class CourseOfferingRead(CourseOfferingBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


__all__ = [
    "FacultyBase", "FacultyCreate", "FacultyUpdate", "FacultyRead",
    "SubjectBase", "SubjectCreate", "SubjectUpdate", "SubjectRead",
    "CourseOfferingBase", "CourseOfferingCreate",
    "CourseOfferingUpdate", "CourseOfferingRead",
]