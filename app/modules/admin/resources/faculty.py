"""faculty admin resource."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.common.crud import Hooks, ResourceConfig
from app.modules.admin.fk import count_blockers, ensure_exists
from app.modules.admin.schemas import FacultyCreate, FacultyRead, FacultyUpdate
from app.modules.faculty.models import Faculty
from app.modules.students.models import Program


def _row_mapper(f: Faculty) -> dict[str, Any]:
    return {
        "id": f.id,
        "name": f.name,
        "email": f.email,
        "ktu_id": getattr(f, "ktu_id", None),
        "department_id": getattr(f, "department_id", None),
        "is_active": getattr(f, "is_active", True),
        "created_at": f.created_at,
        "updated_at": f.updated_at,
        "deleted_at": f.deleted_at,
        "program_code": f.department.code if getattr(f, "department", None) else None,
    }


def _validate_fks(data: dict, db: Session) -> None:
    if data.get("department_id") is not None:
        ensure_exists(db, Program, data["department_id"], field_name="department_id")


def _before_create(data: dict, db: Session, user: Any) -> dict:
    _validate_fks(data, db)
    return data


def _before_update(obj: Faculty, data: dict, db: Session, user: Any) -> dict:
    _validate_fks(data, db)
    return data


def _check_delete(obj: Faculty, db: Session) -> list[str]:
    blockers: list[str] = []
    try:
        from app.modules.course_offerings.models import CourseOffering  # type: ignore
        n = count_blockers(db, CourseOffering, CourseOffering.faculty_id, obj.id)
        if n:
            blockers.append(f"{n} course offering(s)")
    except Exception:  # pragma: no cover
        pass
    return blockers


CONFIG = ResourceConfig(
    name="faculty",
    model=Faculty,
    read_schema=FacultyRead,
    create_schema=FacultyCreate,
    update_schema=FacultyUpdate,
    search_fields=(Faculty.name, Faculty.email),
    filter_fields={
        "department_id": Faculty.department_id,
        "is_active": Faculty.is_active,
    },
    sortable_fields={
        "name": Faculty.name,
        "email": Faculty.email,
        "created_at": Faculty.created_at,
    },
    load_options=(selectinload(Faculty.department),)
    if hasattr(Faculty, "department")
    else (),
    row_mapper=_row_mapper,
    check_delete=_check_delete,
    hooks=Hooks(before_create=_before_create, before_update=_before_update),
)