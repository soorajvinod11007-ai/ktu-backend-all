"""subjects admin resource."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.common.crud import Hooks, ResourceConfig
from app.modules.admin.fk import count_blockers
from app.modules.admin.schemas import SubjectCreate, SubjectRead, SubjectUpdate
from app.modules.faculty.models import Subject


def _row_mapper(s: Subject) -> dict[str, Any]:
    return {
        "id": s.id,
        "code": s.code,
        "name": s.name,
        "semester": s.semester,
        "scheme": s.scheme,
        "type": getattr(s, "type", getattr(s, "subject_type", None)),
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "deleted_at": s.deleted_at,
    }


def _check_delete(obj: Subject, db: Session) -> list[str]:
    blockers: list[str] = []
    try:
        from app.modules.course_offerings.models import CourseOffering  # type: ignore
        n = count_blockers(db, CourseOffering, CourseOffering.subject_id, obj.id)
        if n:
            blockers.append(f"{n} course offering(s)")
    except Exception:  # pragma: no cover
        pass
    try:
        from app.modules.results.models import SemesterResult  # type: ignore
        n = count_blockers(db, SemesterResult, SemesterResult.subject_id, obj.id)
        if n:
            blockers.append(f"{n} result(s)")
    except Exception:  # pragma: no cover
        pass
    return blockers


_type_col = getattr(Subject, "type", None) or getattr(Subject, "subject_type", None)

CONFIG = ResourceConfig(
    name="subjects",
    model=Subject,
    read_schema=SubjectRead,
    create_schema=SubjectCreate,
    update_schema=SubjectUpdate,
    search_fields=(Subject.code, Subject.name),
    filter_fields={
        "semester": Subject.semester,
        "scheme": Subject.scheme,
        "type": _type_col,
    },
    sortable_fields={
        "code": Subject.code,
        "name": Subject.name,
        "semester": Subject.semester,
        "created_at": Subject.created_at,
    },
    row_mapper=_row_mapper,
    check_delete=_check_delete,
    hooks=Hooks(),
)