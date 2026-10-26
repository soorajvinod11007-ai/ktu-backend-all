"""programs admin resource."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.common.crud import Hooks, ResourceConfig
from app.modules.admin.fk import count_blockers
from app.modules.admin.schemas import ProgramCreate, ProgramRead, ProgramUpdate
from app.modules.students.models import Division, Program, Student


def _row_mapper(p: Program) -> dict[str, Any]:
    return {
        "id": p.id,
        "code": p.code,
        "name": p.name,
        "is_active": p.is_active,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "deleted_at": p.deleted_at,
    }


def _check_delete(obj: Program, db: Session) -> list[str]:
    blockers: list[str] = []
    n = count_blockers(db, Student, Student.program_id, obj.id)
    if n:
        blockers.append(f"{n} student(s)")
    n = count_blockers(db, Division, Division.program_id, obj.id)
    if n:
        blockers.append(f"{n} division(s)")
    return blockers


CONFIG = ResourceConfig(
    name="programs",
    model=Program,
    read_schema=ProgramRead,
    create_schema=ProgramCreate,
    update_schema=ProgramUpdate,
    search_fields=(Program.code, Program.name),
    filter_fields={"is_active": Program.is_active},
    sortable_fields={
        "code": Program.code,
        "name": Program.name,
        "is_active": Program.is_active,
        "created_at": Program.created_at,
    },
    row_mapper=_row_mapper,
    check_delete=_check_delete,
    hooks=Hooks(),
)