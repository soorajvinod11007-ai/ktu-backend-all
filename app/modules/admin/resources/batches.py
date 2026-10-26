"""batches admin resource."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.common.crud import Hooks, ResourceConfig
from app.modules.admin.fk import count_blockers
from app.modules.admin.schemas import BatchCreate, BatchRead, BatchUpdate
from app.modules.students.models import Batch, Division, Student


def _row_mapper(b: Batch) -> dict[str, Any]:
    return {
        "id": b.id,
        "start_year": b.start_year,
        "end_year": b.end_year,
        "label": b.label,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
        "deleted_at": b.deleted_at,
    }


def _check_delete(obj: Batch, db: Session) -> list[str]:
    blockers: list[str] = []
    n = count_blockers(db, Student, Student.batch_id, obj.id)
    if n:
        blockers.append(f"{n} student(s)")
    n = count_blockers(db, Division, Division.batch_id, obj.id)
    if n:
        blockers.append(f"{n} division(s)")
    return blockers


CONFIG = ResourceConfig(
    name="batches",
    model=Batch,
    read_schema=BatchRead,
    create_schema=BatchCreate,
    update_schema=BatchUpdate,
    search_fields=(Batch.label,),
    filter_fields={"start_year": Batch.start_year, "end_year": Batch.end_year},
    sortable_fields={
        "label": Batch.label,
        "start_year": Batch.start_year,
        "end_year": Batch.end_year,
        "created_at": Batch.created_at,
    },
    row_mapper=_row_mapper,
    check_delete=_check_delete,
    hooks=Hooks(),
)