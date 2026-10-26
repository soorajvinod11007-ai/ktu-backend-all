# common/base
"""Soft-delete mixin and a generic repository used by all modules."""

import uuid
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy import DateTime, func, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class TimestampMixin:
    """Adds id + audit columns with soft-delete support."""

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class BaseRepository(Generic[ModelType]):
    """Generic CRUD repository.

    All queries filter out soft-deleted rows unless the caller explicitly
    asks otherwise. `flush()` is used so callers can read generated ids
    without committing — commit is owned by the request lifecycle.
    """

    model: type[ModelType]

    def __init__(self, model: type[ModelType], db: Session) -> None:
        self.model = model
        self.db = db

    # --- reads ---
    def get(self, obj_id: uuid.UUID, *, include_deleted: bool = False) -> ModelType | None:
        stmt = select(self.model).where(self.model.id == obj_id)  # type: ignore[attr-defined]
        if not include_deleted:
            stmt = stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by(self, **filters: Any) -> ModelType | None:
        stmt = select(self.model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        stmt = stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        return self.db.execute(stmt).scalar_one_or_none()

    def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[ModelType]:
        stmt = select(self.model)
        if not include_deleted:
            stmt = stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        stmt = stmt.offset(skip).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    # --- writes ---
    def create(self, **data: Any) -> ModelType:
        obj = self.model(**data)  # type: ignore[call-arg]
        self.db.add(obj)
        self.db.flush()
        return obj

    def update(self, obj: ModelType, **data: Any) -> ModelType:
        for key, value in data.items():
            setattr(obj, key, value)
        self.db.flush()
        return obj

    def soft_delete(self, obj: ModelType) -> ModelType:
        obj.deleted_at = datetime.now(tz=timezone.utc)  # type: ignore[attr-defined]
        self.db.flush()
        return obj