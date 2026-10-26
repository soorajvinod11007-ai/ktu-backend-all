"""course-offerings admin resource. Search matches Subject.code via a join."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.common.crud import Hooks, ResourceConfig
from app.modules.admin.fk import ensure_exists
from app.modules.admin.schemas import (
    CourseOfferingCreate,
    CourseOfferingRead,
    CourseOfferingUpdate,
)
from app.modules.faculty.models import CourseOffering
from app.modules.faculty.models import Faculty
from app.modules.students.models import Batch, Division, Program
from app.modules.faculty.models import Subject


def _base_query(stmt):
    # Join Subject so search can match on subject code + name.
    return stmt.join(Subject, CourseOffering.subject_id == Subject.id)


def _row_mapper(c: CourseOffering) -> dict[str, Any]:
    return {
        "id": c.id,
        "program_id": c.program_id,
        "batch_id": c.batch_id,
        "division_id": c.division_id,
        "subject_id": c.subject_id,
        "faculty_id": c.faculty_id,
        "semester": c.semester,
        "academic_year": c.academic_year,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "deleted_at": c.deleted_at,
        "subject_code": c.subject.code if getattr(c, "subject", None) else None,
        "subject_name": c.subject.name if getattr(c, "subject", None) else None,
        "faculty_name": c.faculty.name if getattr(c, "faculty", None) else None,
        "program_code": c.program.code if getattr(c, "program", None) else None,
        "batch_label": c.batch.label if getattr(c, "batch", None) else None,
        "division_name": c.division.name if getattr(c, "division", None) else None,
    }


def _validate_fks(data: dict, db: Session) -> None:
    if data.get("program_id") is not None:
        ensure_exists(db, Program, data["program_id"], field_name="program_id")
    if data.get("batch_id") is not None:
        ensure_exists(db, Batch, data["batch_id"], field_name="batch_id")
    if data.get("division_id") is not None:
        ensure_exists(db, Division, data["division_id"], field_name="division_id")
    if data.get("subject_id") is not None:
        ensure_exists(db, Subject, data["subject_id"], field_name="subject_id")
    if data.get("faculty_id") is not None:
        ensure_exists(db, Faculty, data["faculty_id"], field_name="faculty_id")


def _before_create(data: dict, db: Session, user: Any) -> dict:
    _validate_fks(data, db)
    return data


def _before_update(obj: CourseOffering, data: dict, db: Session, user: Any) -> dict:
    _validate_fks(data, db)
    return data


CONFIG = ResourceConfig(
    name="course-offerings",
    model=CourseOffering,
    read_schema=CourseOfferingRead,
    create_schema=CourseOfferingCreate,
    update_schema=CourseOfferingUpdate,
    search_fields=(Subject.code, Subject.name),
    filter_fields={
        "program_id": CourseOffering.program_id,
        "batch_id": CourseOffering.batch_id,
        "division_id": CourseOffering.division_id,
        "semester": CourseOffering.semester,
        "academic_year": CourseOffering.academic_year,
        "faculty_id": CourseOffering.faculty_id,
    },
    sortable_fields={
        "semester": CourseOffering.semester,
        "academic_year": CourseOffering.academic_year,
        "created_at": CourseOffering.created_at,
    },
    load_options=tuple(
        selectinload(getattr(CourseOffering, rel))
        for rel in ("subject", "faculty", "program", "batch", "division")
        if hasattr(CourseOffering, rel)
    ),
    base_query=_base_query,
    row_mapper=_row_mapper,
    hooks=Hooks(before_create=_before_create, before_update=_before_update),
)