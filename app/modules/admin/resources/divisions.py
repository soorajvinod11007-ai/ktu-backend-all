"""divisions admin resource."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.common.crud import Hooks, ResourceConfig
from app.core.exceptions import ValidationFailedError
from app.modules.admin.fk import count_blockers, ensure_exists
from app.modules.admin.schemas import DivisionCreate, DivisionRead, DivisionUpdate
from app.modules.students.models import Batch, Division, Program, Student


def _row_mapper(d: Division) -> dict[str, Any]:
    return {
        "id": d.id,
        "program_id": d.program_id,
        "batch_id": d.batch_id,
        "name": d.name,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
        "deleted_at": d.deleted_at,
        "program_code": d.program.code if d.program else None,
        "batch_label": d.batch.label if d.batch else None,
    }


def _validate_fks(data: dict, db: Session) -> None:
    if "program_id" in data:
        ensure_exists(db, Program, data["program_id"], field_name="program_id")
    if "batch_id" in data:
        ensure_exists(db, Batch, data["batch_id"], field_name="batch_id")


def _before_create(data: dict, db: Session, user: Any) -> dict:
    _validate_fks(data, db)
    return data


def _before_update(obj: Division, data: dict, db: Session, user: Any) -> dict:
    _validate_fks(data, db)
    return data


def _check_delete(obj: Division, db: Session) -> list[str]:
    blockers: list[str] = []
    n = count_blockers(db, Student, Student.division_id, obj.id)
    if n:
        blockers.append(f"{n} student(s)")
    # Course offerings reference divisions too — import lazily to avoid a cycle.
    try:
        from app.modules.course_offerings.models import CourseOffering  # type: ignore
        n = count_blockers(db, CourseOffering, CourseOffering.division_id, obj.id)
        if n:
            blockers.append(f"{n} course offering(s)")
    except Exception:  # pragma: no cover
        pass
    return blockers


CONFIG = ResourceConfig(
    name="divisions",
    model=Division,
    read_schema=DivisionRead,
    create_schema=DivisionCreate,
    update_schema=DivisionUpdate,
    search_fields=(Division.name,),
    filter_fields={"program_id": Division.program_id, "batch_id": Division.batch_id},
    sortable_fields={
        "name": Division.name,
        "created_at": Division.created_at,
    },
    load_options=(selectinload(Division.program), selectinload(Division.batch)),
    row_mapper=_row_mapper,
    check_delete=_check_delete,
    hooks=Hooks(before_create=_before_create, before_update=_before_update),
)