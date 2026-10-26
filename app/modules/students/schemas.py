# students/schemas
"""Pydantic v2 schemas for programs, batches, divisions, students."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.students.models import StudentStatus


# --------------------------------------------------------------------------- #
# Program
# --------------------------------------------------------------------------- #
class ProgramBase(BaseModel):
    code: str = Field(min_length=2, max_length=4)
    name: str = Field(min_length=1, max_length=255)
    is_active: bool = True


class ProgramCreate(ProgramBase):
    pass


class ProgramUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=4)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class ProgramRead(ProgramBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Batch
# --------------------------------------------------------------------------- #
class BatchBase(BaseModel):
    start_year: int = Field(ge=2000, le=2100)
    end_year: int = Field(ge=2001, le=2101)
    label: str = Field(min_length=4, max_length=16)


class BatchCreate(BatchBase):
    pass


class BatchUpdate(BaseModel):
    start_year: int | None = Field(default=None, ge=2000, le=2100)
    end_year: int | None = Field(default=None, ge=2001, le=2101)
    label: str | None = Field(default=None, min_length=4, max_length=16)


class BatchRead(BatchBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Division
# --------------------------------------------------------------------------- #
class DivisionBase(BaseModel):
    program_id: uuid.UUID
    batch_id: uuid.UUID
    name: str = Field(min_length=1, max_length=16)


class DivisionCreate(DivisionBase):
    pass


class DivisionUpdate(BaseModel):
    program_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=16)


class DivisionRead(DivisionBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Student
# --------------------------------------------------------------------------- #
class StudentBase(BaseModel):
    register_no: str = Field(min_length=8, max_length=16)
    name: str = Field(min_length=1, max_length=255)
    program_id: uuid.UUID
    batch_id: uuid.UUID
    division_id: uuid.UUID | None = None
    status: StudentStatus = StudentStatus.ACTIVE
    is_flagged: bool = False


class StudentCreate(StudentBase):
    pass


class StudentUpdate(BaseModel):
    register_no: str | None = Field(default=None, min_length=8, max_length=16)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    program_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    division_id: uuid.UUID | None = None
    status: StudentStatus | None = None
    is_flagged: bool | None = None


class StudentRead(StudentBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


__all__ = [
    "ProgramBase", "ProgramCreate", "ProgramUpdate", "ProgramRead",
    "BatchBase", "BatchCreate", "BatchUpdate", "BatchRead",
    "DivisionBase", "DivisionCreate", "DivisionUpdate", "DivisionRead",
    "StudentBase", "StudentCreate", "StudentUpdate", "StudentRead",
]