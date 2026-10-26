"""grade-cards admin resource."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.common.crud import Hooks, ResourceConfig
from app.modules.admin.fk import ensure_exists
from app.modules.admin.schemas import GradeCardCreate, GradeCardRead, GradeCardUpdate
from app.modules.results.models import GradeCard, ExamSession  # type: ignore
from app.modules.students.models import Student


def _row_mapper(g: GradeCard) -> dict[str, Any]:
    return {
        "id": g.id,
        "student_id": g.student_id,
        "semester": g.semester,
        "exam_session_id": g.exam_session_id,
        "created_at": g.created_at,
        "updated_at": g.updated_at,
        "deleted_at": g.deleted_at,
        "student_name": g.student.name if getattr(g, "student", None) else None,
        "register_no": g.student.register_no if getattr(g, "student", None) else None,
        "exam_type": g.exam_session.exam_type
        if getattr(g, "exam_session", None)
        else None,
    }


def _validate_fks(data: dict, db: Session) -> None:
    if data.get("student_id") is not None:
        ensure_exists(db, Student, data["student_id"], field_name="student_id")
    if data.get("exam_session_id") is not None:
        ensure_exists(
            db, ExamSession, data["exam_session_id"], field_name="exam_session_id"
        )


def _before_create(data: dict, db: Session, user: Any) -> dict:
    _validate_fks(data, db)
    return data


def _before_update(obj: GradeCard, data: dict, db: Session, user: Any) -> dict:
    _validate_fks(data, db)
    return data


CONFIG = ResourceConfig(
    name="grade-cards",
    model=GradeCard,
    read_schema=GradeCardRead,
    create_schema=GradeCardCreate,
    update_schema=GradeCardUpdate,
    filter_fields={
        "student_id": GradeCard.student_id,
        "semester": GradeCard.semester,
        "exam_session_id": GradeCard.exam_session_id,
    },
    sortable_fields={
        "semester": GradeCard.semester,
        "created_at": GradeCard.created_at,
    },
    load_options=tuple(
        selectinload(getattr(GradeCard, rel))
        for rel in ("student", "exam_session")
        if hasattr(GradeCard, rel)
    ),
    row_mapper=_row_mapper,
    hooks=Hooks(before_create=_before_create, before_update=_before_update),
)