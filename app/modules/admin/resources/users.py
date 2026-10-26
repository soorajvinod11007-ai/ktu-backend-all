"""users admin resource: password hashing, self/last-admin protection."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.crud import Hooks, ResourceConfig
from app.core.exceptions import ConflictError, PermissionDeniedError
from app.core.security import hash_password
from app.modules.admin.schemas import UserCreate, UserRead, UserUpdate
from app.modules.auth.models import User, UserRole


def _count_other_active_admins(db: Session, exclude_id: Any) -> int:
    stmt = select(func.count()).select_from(User).where(
        User.role == UserRole.ADMIN,
        User.is_active.is_(True),
        User.deleted_at.is_(None),
        User.id != exclude_id,
    )
    return int(db.execute(stmt).scalar_one())


def _row_mapper(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "full_name": getattr(u, "full_name", None),
        "role": u.role,
        "is_active": u.is_active,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
        "deleted_at": u.deleted_at,
    }


def _before_create(data: dict, db: Session, user: Any) -> dict:
    pw = data.pop("password", None)
    if pw:
        data["hashed_password"] = hash_password(pw)
    return data


def _before_update(obj: User, data: dict, db: Session, user: Any) -> dict:
    # Admin cannot deactivate or demote themselves.
    if obj.id == user.id:
        if data.get("is_active") is False:
            raise PermissionDeniedError("You cannot deactivate your own account.")
        if "role" in data and data["role"] != UserRole.ADMIN:
            raise PermissionDeniedError("You cannot change your own role.")

    demoting = "role" in data and data["role"] != UserRole.ADMIN
    deactivating = data.get("is_active") is False
    if obj.role == UserRole.ADMIN and obj.is_active and (demoting or deactivating):
        if _count_other_active_admins(db, obj.id) == 0:
            raise ConflictError("Cannot demote or deactivate the last active admin.")

    pw = data.pop("password", None)
    if pw:
        data["hashed_password"] = hash_password(pw)
    return data


def _before_delete(obj: User, db: Session, user: Any) -> None:
    if obj.id == user.id:
        raise PermissionDeniedError("You cannot delete your own account.")
    if obj.role == UserRole.ADMIN and obj.is_active:
        if _count_other_active_admins(db, obj.id) == 0:
            raise ConflictError("Cannot delete the last active admin.")


CONFIG = ResourceConfig(
    name="users",
    model=User,
    read_schema=UserRead,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    search_fields=(User.username, User.email),
    filter_fields={"role": User.role, "is_active": User.is_active},
    sortable_fields={
        "username": User.username,
        "email": User.email,
        "role": User.role,
        "is_active": User.is_active,
        "created_at": User.created_at,
    },
    row_mapper=_row_mapper,
    hooks=Hooks(
        before_create=_before_create,
        before_update=_before_update,
        before_delete=_before_delete,
    ),
    audit_exclude=frozenset({"hashed_password"}),
)