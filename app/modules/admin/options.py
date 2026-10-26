"""GET /admin/options/{resource} — typeahead dropdown helper.

Returns ``[{"id": ..., "label": ...}]`` with no pagination. Supported
resources: programs, batches, divisions, students, faculty, subjects,
exam-sessions. Always applies the soft-delete filter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.modules.auth.dependencies import require_admin
from app.modules.results.models import ExamSession
from app.modules.faculty.models import Faculty
from app.modules.students.models import Batch, Division, Program, Student
from app.modules.faculty.models import Subject
from app.modules.auth.models import User


@dataclass(frozen=True)
class OptionSource:
    model: type
    label_fn: Callable[[Any], str]
    search_columns: tuple[Any, ...]
    load_options: tuple[Any, ...] = ()


def _division_label(d: Division) -> str:
    prog = d.program.code if getattr(d, "program", None) else "?"
    batch = d.batch.label if getattr(d, "batch", None) else "?"
    return f"{prog}/{batch}/{d.name}"


OPTION_SOURCES: dict[str, OptionSource] = {
    "programs": OptionSource(
        model=Program,
        label_fn=lambda p: f"{p.code} — {p.name}",
        search_columns=(Program.code, Program.name),
    ),
    "batches": OptionSource(
        model=Batch,
        label_fn=lambda b: b.label,
        search_columns=(Batch.label,),
    ),
    "divisions": OptionSource(
        model=Division,
        label_fn=_division_label,
        search_columns=(Division.name,),
        load_options=(selectinload(Division.program), selectinload(Division.batch)),
    ),
    "students": OptionSource(
        model=Student,
        label_fn=lambda s: f"{s.register_no} — {s.name}",
        search_columns=(Student.register_no, Student.name),
    ),
    "faculty": OptionSource(
        model=Faculty,
        label_fn=lambda f: f.name,
        search_columns=(Faculty.name, Faculty.email),
    ),
    "subjects": OptionSource(
        model=Subject,
        label_fn=lambda s: f"{s.code} — {s.name}",
        search_columns=(Subject.code, Subject.name),
    ),
    "exam-sessions": OptionSource(
        model=ExamSession,
        label_fn=lambda e: e.name,
        search_columns=(ExamSession.name,),
    ),
    "users": OptionSource(
        model=User,
        label_fn=lambda u: u.username,
        search_columns=(User.username, User.email),
    ),
}


def list_options(
    resource: str,
    db: Session,
    q: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    src = OPTION_SOURCES.get(resource)
    if src is None:
        raise NotFoundError(f"Options are not available for {resource!r}.")

    settings = get_settings()
    cap = int(getattr(settings, "ADMIN_OPTIONS_LIMIT", 50))
    size = min(limit if limit is not None else cap, cap)

    stmt = select(src.model).where(src.model.deleted_at.is_(None))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(*(col.ilike(pattern) for col in src.search_columns)))
    stmt = stmt.order_by(*src.search_columns).limit(size)
    for opt in src.load_options:
        stmt = stmt.options(opt)

    rows = db.execute(stmt).scalars().unique().all()
    return [{"id": str(row.id), "label": src.label_fn(row)} for row in rows]


__all__ = ["OPTION_SOURCES", "list_options"]