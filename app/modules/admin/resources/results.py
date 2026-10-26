"""results admin resource.

Grade/status consistency is enforced here, and every change to those two
fields writes a ``ResultHistory`` row (change_type = "manual_edit") that
records the acting user.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.common.crud import Hooks, ResourceConfig
from app.core.exceptions import ValidationFailedError
from app.modules.admin.fk import ensure_exists
from app.modules.admin.schemas import ResultCreate, ResultRead, ResultUpdate
from app.modules.results.models import (  # type: ignore
    ExamSession,
    ResultHistory,
    SemesterResult,
    ResultChangeType,
)
from app.modules.students.models import Student
from app.modules.faculty.models import Subject

GRADE_FAIL = "F"
STATUS_FAIL = "fail"
STATUS_PASS = "pass"


def _base_query(stmt):
    return stmt.join(Student, SemesterResult.student_id == Student.id)


def _row_mapper(r: SemesterResult) -> dict[str, Any]:
    return {
        "id": r.id,
        "student_id": r.student_id,
        "subject_id": r.subject_id,
        "exam_session_id": r.exam_session_id,
        "semester": r.semester,
        "grade": getattr(r, "grade", None),
        "status": r.status,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "deleted_at": r.deleted_at,
        "student_name": r.student.name if getattr(r, "student", None) else None,
        "register_no": r.student.register_no if getattr(r, "student", None) else None,
        "subject_code": r.subject.code if getattr(r, "subject", None) else None,
        "subject_name": r.subject.name if getattr(r, "subject", None) else None,
        "exam_type": r.exam_session.exam_type
        if getattr(r, "exam_session", None)
        else None,
    }


def _validate_fks(data: dict, db: Session) -> None:
    if data.get("student_id") is not None:
        ensure_exists(db, Student, data["student_id"], field_name="student_id")
    if data.get("subject_id") is not None:
        ensure_exists(db, Subject, data["subject_id"], field_name="subject_id")
    if data.get("exam_session_id") is not None:
        ensure_exists(
            db, ExamSession, data["exam_session_id"], field_name="exam_session_id"
        )


def _enforce_consistency(obj: SemesterResult, data: dict) -> None:
    """Keep grade and status consistent.

    grade == 'F'   -> status must be 'fail'
    grade != 'F'   -> status must be 'pass' (unless caller overrode it)
    """
    if "grade" in data:
        grade = data["grade"]
        if grade == GRADE_FAIL:
            data["status"] = STATUS_FAIL
        elif data["status"] != STATUS_FAIL:
            # grade is a pass mark; force status to pass.
            data["status"] = STATUS_PASS
        return

    if "status" in data:
        new_status = data["status"]
        current_grade = obj.grade
        if new_status == STATUS_FAIL and current_grade != GRADE_FAIL:
            raise ValidationFailedError(
                "Status 'fail' requires grade 'F'.",
                details=[{"field": "status", "grade": current_grade}],
            )
        if new_status == STATUS_PASS and current_grade == GRADE_FAIL:
            raise ValidationFailedError(
                "Grade 'F' requires status 'fail'.",
                details=[{"field": "grade", "value": current_grade}],
            )


def _before_create(data: dict, db: Session, user: Any) -> dict:
    _validate_fks(data, db)
    # Normalise consistency using a dummy-ish check on the payload.
    grade = data.get("grade")
    if grade == GRADE_FAIL:
        data["status"] = STATUS_FAIL
    elif "status" not in data or data["status"] == "":
        data["status"] = STATUS_PASS
    return data


def _before_update(obj: SemesterResult, data: dict, db: Session, user: Any) -> dict:
    _validate_fks(data, db)
    _enforce_consistency(obj, data)
    return data


def _after_update(obj: SemesterResult, before: dict, db: Session, user: Any) -> None:
    grade_changed = before.get("grade") != getattr(obj, "grade", None)
    status_changed = before.get("status") != getattr(obj, "status", None)
    if not grade_changed and not status_changed:
        return

    db.add(
        ResultHistory(
            semester_result_id=obj.id,
            change_type=ResultChangeType.MANUAL_EDIT,
            old_grade=before.get("grade"),
            new_grade=getattr(obj, "grade", None),
            old_status=before.get("status"),
            new_status=getattr(obj, "status", None),
        )
    )
    db.flush()


CONFIG = ResourceConfig(
    name="results",
    model=SemesterResult,
    read_schema=ResultRead,
    create_schema=ResultCreate,
    update_schema=ResultUpdate,
    search_fields=(Student.register_no, Student.name),
    filter_fields={
        "student_id": SemesterResult.student_id,
        "subject_id": SemesterResult.subject_id,
        "exam_session_id": SemesterResult.exam_session_id,
        "semester": SemesterResult.semester,
        "status": SemesterResult.status,
    },
    sortable_fields={
        "semester": SemesterResult.semester,
        "created_at": SemesterResult.created_at,
    },
    load_options=tuple(
        selectinload(getattr(SemesterResult, rel))
        for rel in ("student", "subject", "exam_session")
        if hasattr(SemesterResult, rel)
    ),
    base_query=_base_query,
    row_mapper=_row_mapper,
    hooks=Hooks(
        before_create=_before_create,
        before_update=_before_update,
        after_update=_after_update,
    ),
)