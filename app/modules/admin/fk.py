"""Shared FK-existence and delete-blocker helpers used by admin resources.

Kept generic so every resource's hooks can reuse them and produce a
consistent 422 for missing FKs and a consistent "what blocks the delete"
message for 409s.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationFailedError


def ensure_exists(
    db: Session,
    model: Any,
    obj_id: Any,
    *,
    field_name: str,
) -> Any | None:
    """Validate the FK target exists and is not soft-deleted.

    Raises ``ValidationFailedError`` (422) with the offending field so the
    frontend can highlight it.
    """
    if obj_id is None:
        return None
    stmt = select(model).where(model.id == obj_id)
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))
    obj = db.execute(stmt).scalar_one_or_none()
    if obj is None:
        raise ValidationFailedError(
            f"{field_name}: referenced {model.__tablename__} {obj_id} not found.",
            details=[{"field": field_name, "value": str(obj_id)}],
        )
    return obj


def count_blockers(db: Session, model: Any, column: Any, value: Any) -> int:
    """Count live rows of ``model`` where ``column == value``.

    Used by ``check_delete`` hooks to decide whether a 409 is warranted.
    """
    stmt = select(func.count()).select_from(model).where(column == value)
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))
    return int(db.execute(stmt).scalar_one())


__all__ = ["ensure_exists", "count_blockers"]