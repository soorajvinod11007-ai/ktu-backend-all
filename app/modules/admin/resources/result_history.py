"""result-history admin resource (read-only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import selectinload

from app.common.crud import ResourceConfig
from app.modules.admin.schemas import ResultHistoryRead
from app.modules.results.models import ResultHistory, SemesterResult  # type: ignore
from app.modules.students.models import Student


def _base_query(stmt):
    # Join SemesterResult -> Student so register_no is filterable/searchable.
    stmt = stmt.join(SemesterResult, ResultHistory.semester_result_id == SemesterResult.id)
    stmt = stmt.join(Student, SemesterResult.student_id == Student.id)
    return stmt


def _row_mapper(h: ResultHistory) -> dict[str, Any]:
    sr = getattr(h, "semester_result", None)
    student = getattr(sr, "student", None) if sr else None
    return {
        "id": h.id,
        "semester_result_id": h.semester_result_id,
        "change_type": h.change_type.value
        if hasattr(h.change_type, "value")
        else h.change_type,
        "changed_by_user_id": getattr(h, "changed_by_user_id", None),
        "old_value": getattr(h, "old_value", None),
        "new_value": getattr(h, "new_value", None),
        "created_at": h.created_at,
        "updated_at": h.updated_at,
        "deleted_at": h.deleted_at,
        "register_no": student.register_no if student else None,
        "student_name": student.name if student else None,
    }


CONFIG = ResourceConfig(
    name="result-history",
    model=ResultHistory,
    read_schema=ResultHistoryRead,
    filter_fields={
        "semester_result_id": ResultHistory.semester_result_id,
    },
    sortable_fields={
        "created_at": ResultHistory.created_at,
    },
    load_options=(
        selectinload(ResultHistory.semester_result).selectinload(
            SemesterResult.student
        ),
    ),
    base_query=_base_query,
    row_mapper=_row_mapper,
    read_only=True,
)