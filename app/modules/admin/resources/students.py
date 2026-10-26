"""students admin resource.

Handles register-number parsing, duplicate detection (including
soft-deleted rows, with a "restore instead" hint) and delete blockers.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.common.crud import Hooks, ResourceConfig
from app.common.register_no import parse_register_no
from app.core.exceptions import DuplicateError
from app.modules.admin.fk import count_blockers, ensure_exists
from app.modules.admin.schemas import StudentCreate, StudentRead, StudentUpdate
from app.modules.students.models import Batch, Division, Program, Student


# --------------------------------------------------------------------------- #
# row mapper
# --------------------------------------------------------------------------- #
def _row_mapper(s: Student) -> dict[str, Any]:
    return {
        "id": s.id,
        "register_no": s.register_no,
        "name": s.name,
        "program_id": s.program_id,
        "batch_id": s.batch_id,
        "division_id": s.division_id,
        "status": s.status,
        "is_flagged": s.is_flagged,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "deleted_at": s.deleted_at,
        "program_code": s.program.code if s.program else None,
        "program_name": s.program.name if s.program else None,
        "batch_label": s.batch.label if s.batch else None,
        "division_name": s.division.name if s.division else None,
    }


# --------------------------------------------------------------------------- #
# register-number handling
# --------------------------------------------------------------------------- #
def _pick(parsed: Any, key: str, default: Any = None) -> Any:
    """Support the helper returning either a dataclass or a mapping."""
    if parsed is None:
        return default
    if isinstance(parsed, dict):
        return parsed.get(key, default)
    return getattr(parsed, key, default)


def _apply_register_parse(data: dict, db: Session) -> None:
    reg = data.get("register_no")
    if not reg:
        return
    parsed = parse_register_no(reg)
    if parsed is None:
        return

    program_code = _pick(parsed, "program_code")
    admission_year = _pick(parsed, "admission_year")
    valid_prefix = _pick(
        parsed,
        "is_valid_prefix",
        _pick(parsed, "valid_prefix", True),
    )

    if not data.get("program_id") and program_code:
        prog = db.execute(
            select(Program).where(
                Program.code == program_code,
                Program.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if prog is not None:
            data["program_id"] = prog.id

    if not data.get("batch_id") and admission_year is not None:
        # accept 2- or 4-digit years
        full_year = 2000 + admission_year if admission_year < 100 else admission_year
        batch = db.execute(
            select(Batch).where(
                Batch.start_year == full_year,
                Batch.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if batch is not None:
            data["batch_id"] = batch.id

    if valid_prefix is False:
        data["is_flagged"] = True


def _check_duplicate_register(
    reg: str, db: Session, exclude_id: Any | None = None
) -> None:
    stmt = select(Student).where(Student.register_no == reg)
    if exclude_id is not None:
        stmt = stmt.where(Student.id != exclude_id)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is None:
        return
    if existing.deleted_at is not None:
        raise DuplicateError(
            f"Register number {reg!r} belongs to a soft-deleted student. "
            f"Restore that record instead of creating a new one.",
            details=[{"existing_id": str(existing.id), "deleted": True}],
        )
    raise DuplicateError(
        f"Register number {reg!r} already exists.",
        details=[{"existing_id": str(existing.id), "deleted": False}],
    )


# --------------------------------------------------------------------------- #
# FK validation
# --------------------------------------------------------------------------- #
def _validate_fks(data: dict, db: Session) -> None:
    if "program_id" in data and data["program_id"] is not None:
        ensure_exists(db, Program, data["program_id"], field_name="program_id")
    if "batch_id" in data and data["batch_id"] is not None:
        ensure_exists(db, Batch, data["batch_id"], field_name="batch_id")
    if "division_id" in data and data["division_id"] is not None:
        ensure_exists(db, Division, data["division_id"], field_name="division_id")


# --------------------------------------------------------------------------- #
# hooks
# --------------------------------------------------------------------------- #
def _before_create(data: dict, db: Session, user: Any) -> dict:
    _check_duplicate_register(data["register_no"], db)
    _apply_register_parse(data, db)
    _validate_fks(data, db)
    data.setdefault("is_flagged", False)
    return data


def _before_update(obj: Student, data: dict, db: Session, user: Any) -> dict:
    if "register_no" in data and data["register_no"] != obj.register_no:
        _check_duplicate_register(data["register_no"], db, exclude_id=obj.id)
        _apply_register_parse(data, db)
    _validate_fks(data, db)
    return data


def _check_delete(obj: Student, db: Session) -> list[str]:
    blockers: list[str] = []
    try:
        from app.modules.results.models import GradeCard, SemesterResult  # type: ignore
        n = count_blockers(db, SemesterResult, SemesterResult.student_id, obj.id)
        if n:
            blockers.append(f"{n} result(s)")
        n = count_blockers(db, GradeCard, GradeCard.student_id, obj.id)
        if n:
            blockers.append(f"{n} grade card(s)")
    except Exception:  # pragma: no cover
        pass
    return blockers


CONFIG = ResourceConfig(
    name="students",
    model=Student,
    read_schema=StudentRead,
    create_schema=StudentCreate,
    update_schema=StudentUpdate,
    search_fields=(Student.register_no, Student.name),
    filter_fields={
        "program_id": Student.program_id,
        "batch_id": Student.batch_id,
        "division_id": Student.division_id,
        "status": Student.status,
        "is_flagged": Student.is_flagged,
    },
    sortable_fields={
        "register_no": Student.register_no,
        "name": Student.name,
        "status": Student.status,
        "is_flagged": Student.is_flagged,
        "created_at": Student.created_at,
    },
    load_options=(
        selectinload(Student.program),
        selectinload(Student.batch),
        selectinload(Student.division),
    ),
    row_mapper=_row_mapper,
    check_delete=_check_delete,
    hooks=Hooks(before_create=_before_create, before_update=_before_update),
)