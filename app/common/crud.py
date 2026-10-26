"""Generic admin CRUD framework.

Every admin resource is described by a single :class:`ResourceConfig`.
From that config the framework derives a repository (query building),
a service (hooks, audit, transaction boundaries), and — in
``app.common.crud_router`` — the route handlers. Result: all resources
share identical list/filter/sort/pagination semantics, so the frontend
can render one table screen.

Layering rule: routers call services, services call repositories.
Routers never touch the session directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterator, Sequence, TypeVar

from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, inspect, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.base import BaseRepository
from app.common.filters import parse_filters
from app.common.pagination import PageParams
from app.common.sorting import parse_sort
from app.core.config import get_settings
from app.core.database import Base
from app.core.exceptions import (
    ConflictError,
    DuplicateError,
    NotFoundError,
    ValidationFailedError,
)

ModelType = TypeVar("ModelType", bound=Base)

_SENSITIVE_FIELDS = frozenset({"hashed_password", "password", "password_hash"})


# --------------------------------------------------------------------------- #
# Hook type aliases
# --------------------------------------------------------------------------- #
BeforeCreateHook = Callable[[dict[str, Any], Session, Any], dict[str, Any] | None]
AfterCreateHook = Callable[[Any, Session, Any], None]
BeforeUpdateHook = Callable[[Any, dict[str, Any], Session, Any], dict[str, Any] | None]
AfterUpdateHook = Callable[[Any, dict[str, Any], Session, Any], None]
ObjectHook = Callable[[Any, Session, Any], None]
DeleteCheckHook = Callable[[Any, Session], list[str]]


@dataclass
class Hooks:
    before_create: BeforeCreateHook | None = None
    after_create: AfterCreateHook | None = None
    before_update: BeforeUpdateHook | None = None
    after_update: AfterUpdateHook | None = None
    before_delete: ObjectHook | None = None
    after_delete: ObjectHook | None = None
    before_restore: ObjectHook | None = None
    after_restore: ObjectHook | None = None


# --------------------------------------------------------------------------- #
# Resource config
# --------------------------------------------------------------------------- #
@dataclass
class ResourceConfig:
    name: str
    model: type
    read_schema: type[BaseModel]

    create_schema: type[BaseModel] | None = None
    update_schema: type[BaseModel] | None = None

    search_fields: Sequence[ColumnElement] = ()
    filter_fields: dict[str, ColumnElement] = field(default_factory=dict)
    sortable_fields: dict[str, ColumnElement] = field(default_factory=dict)
    default_sort: str = "-created_at"

    read_only: bool = False
    load_options: Sequence[Any] = ()
    base_query: Callable[[Any], Any] | None = None
    row_mapper: Callable[[Any], dict] | None = None
    check_delete: DeleteCheckHook | None = None
    hooks: Hooks = field(default_factory=Hooks)
    audit_exclude: frozenset[str] = frozenset()
    audit_writer: Callable[..., None] | None = None

    # Public columns to emit in export. When None, the read_schema field
    # order is used (which already excludes hashed_password).
    export_fields: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.read_only:
            return
        if self.create_schema is None or self.update_schema is None:
            raise ValueError(
                f"Resource {self.name!r} is writable but is missing create/update schemas."
            )


# --------------------------------------------------------------------------- #
# Repository
# --------------------------------------------------------------------------- #
class CrudRepository(BaseRepository[ModelType]):
    def __init__(self, config: ResourceConfig, db: Session) -> None:
        super().__init__(config.model, db)  # type: ignore[arg-type]
        self.config = config

    # --- internal ---
    def _base_select(self):
        stmt = select(self.config.model)
        if self.config.base_query is not None:
            stmt = self.config.base_query(stmt)
        return stmt

    def _apply_common(
        self,
        stmt,
        *,
        include_deleted: bool,
        search: str | None,
        filters: dict[str, Any],
    ):
        if not include_deleted:
            stmt = stmt.where(self.config.model.deleted_at.is_(None))  # type: ignore[attr-defined]

        if search and self.config.search_fields:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(*(col.ilike(pattern) for col in self.config.search_fields))
            )

        for key, value in filters.items():
            stmt = stmt.where(self.config.filter_fields[key] == value)

        return stmt

    # --- reads ---
    def count(
        self,
        *,
        include_deleted: bool,
        search: str | None,
        filters: dict[str, Any],
    ) -> int:
        stmt = self._apply_common(
            self._base_select(),
            include_deleted=include_deleted,
            search=search,
            filters=filters,
        )
        subquery = stmt.order_by(None).subquery()
        return int(
            self.db.execute(select(func.count()).select_from(subquery)).scalar_one()
        )

    def list_page(
        self,
        *,
        include_deleted: bool,
        search: str | None,
        filters: dict[str, Any],
        sort_exprs: list,
        offset: int,
        limit: int,
    ) -> list[ModelType]:
        stmt = self._apply_common(
            self._base_select(),
            include_deleted=include_deleted,
            search=search,
            filters=filters,
        )
        if sort_exprs:
            stmt = stmt.order_by(*sort_exprs)
        stmt = stmt.offset(offset).limit(limit)
        for opt in self.config.load_options:
            stmt = stmt.options(opt)
        result = self.db.execute(stmt).scalars().unique().all()
        return list(result)

    def get_one(
        self,
        obj_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> ModelType | None:
        stmt = self._base_select().where(self.config.model.id == obj_id)  # type: ignore[attr-defined]
        if not include_deleted:
            stmt = stmt.where(self.config.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        for opt in self.config.load_options:
            stmt = stmt.options(opt)
        return self.db.execute(stmt).scalars().unique().one_or_none()

    def iter_all(
        self,
        *,
        include_deleted: bool,
        search: str | None,
        filters: dict[str, Any],
        sort_exprs: list,
        cap: int,
    ) -> Iterator[ModelType]:
        """Yield rows lazily, capped at ``cap``. Overflow is detected
        upstream by :meth:`CrudService.export_rows` via a count query."""
        stmt = self._apply_common(
            self._base_select(),
            include_deleted=include_deleted,
            search=search,
            filters=filters,
        )
        if sort_exprs:
            stmt = stmt.order_by(*sort_exprs)
        stmt = stmt.limit(cap)
        for opt in self.config.load_options:
            stmt = stmt.options(opt)
        # NOTE: yield_per() cannot be combined with unique() (which is needed
        # whenever eager-load options are present and SQLAlchemy deduplicates
        # joined rows).  The export cap (EXPORT_ROW_CAP, default 10 000) keeps
        # the memory cost acceptable without streaming.
        yield from self.db.execute(stmt).scalars().unique().all()


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class CrudService:
    def __init__(self, config: ResourceConfig, db: Session, user: Any) -> None:
        self.config = config
        self.db = db
        self.user = user
        self.repo = CrudRepository(config, db)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def list(
        self,
        *,
        params: PageParams,
        search: str | None,
        sort: str | None,
        include_deleted: bool,
        raw_filters: dict[str, str],
    ) -> dict[str, Any]:
        filters = parse_filters(raw_filters, self.config.filter_fields)
        sort_exprs = parse_sort(
            sort, self.config.sortable_fields, self.config.default_sort
        )

        total = self.repo.count(
            include_deleted=include_deleted, search=search, filters=filters
        )
        items = self.repo.list_page(
            include_deleted=include_deleted,
            search=search,
            filters=filters,
            sort_exprs=sort_exprs,
            offset=params.offset,
            limit=params.page_size,
        )
        return {
            "items": [self._serialize(item) for item in items],
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
        }

    def get(self, obj_id: uuid.UUID) -> BaseModel:
        obj = self.repo.get_one(obj_id)
        if obj is None:
            raise NotFoundError(f"{self.config.name} {obj_id} not found.")
        return self._serialize(obj)

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def export_rows(
        self,
        *,
        include_deleted: bool,
        search: str | None,
        sort: str | None,
        raw_filters: dict[str, str],
    ) -> Iterator[tuple[tuple[str, ...], Iterator[list[Any]]]]:
        """Return ``(headers, row_iterator)`` for the *current* filtered list.

        Pagination is intentionally ignored. If the filtered set exceeds
        ``ADMIN_EXPORT_ROW_CAP`` we raise 422 before any bytes stream, so
        the client never receives a truncated workbook.
        """
        settings = get_settings()
        cap = int(getattr(settings, "ADMIN_EXPORT_ROW_CAP", 50_000))

        filters = parse_filters(raw_filters, self.config.filter_fields)
        sort_exprs = parse_sort(
            sort, self.config.sortable_fields, self.config.default_sort
        )

        total = self.repo.count(
            include_deleted=include_deleted, search=search, filters=filters
        )
        if total > cap:
            raise ValidationFailedError(
                f"Export matches {total} rows which exceeds the cap of {cap}. "
                "Narrow the filters and try again.",
                details=[{"total": total, "cap": cap}],
            )

        headers = self._export_headers()

        def _rows() -> Iterator[list[Any]]:
            for obj in self.repo.iter_all(
                include_deleted=include_deleted,
                search=search,
                filters=filters,
                sort_exprs=sort_exprs,
                cap=cap,
            ):
                serialized = self._serialize(obj)
                yield [getattr(serialized, h) for h in headers]

        return headers, _rows()

    def _export_headers(self) -> tuple[str, ...]:
        if self.config.export_fields is not None:
            return self.config.export_fields
        return tuple(self.config.read_schema.model_fields.keys())

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def create(self, payload: dict[str, Any]) -> BaseModel:
        self._ensure_writable()

        data = dict(payload)
        if self.config.hooks.before_create:
            data = self.config.hooks.before_create(data, self.db, self.user) or data

        try:
            with self.db.begin_nested():
                obj = self.repo.create(**data)
        except IntegrityError as exc:
            raise DuplicateError(self._integrity_message(exc))

        if self.config.hooks.after_create:
            self.config.hooks.after_create(obj, self.db, self.user)

        self._audit("create", obj, changes={"after": self._snapshot(obj)})
        self.db.flush()
        return self._serialize(obj)

    def update(self, obj_id: uuid.UUID, payload: dict[str, Any]) -> BaseModel:
        self._ensure_writable()

        obj = self.repo.get_one(obj_id)
        if obj is None:
            raise NotFoundError(f"{self.config.name} {obj_id} not found.")

        before = self._snapshot(obj)
        data = dict(payload)
        if self.config.hooks.before_update:
            data = (
                self.config.hooks.before_update(obj, data, self.db, self.user) or data
            )

        try:
            with self.db.begin_nested():
                self.repo.update(obj, **data)
        except IntegrityError as exc:
            raise DuplicateError(self._integrity_message(exc))

        if self.config.hooks.after_update:
            self.config.hooks.after_update(obj, before, self.db, self.user)

        after = self._snapshot(obj)
        changes = self._diff(before, after)
        if changes:
            self._audit("update", obj, changes=changes)

        return self._serialize(obj)

    def delete(self, obj_id: uuid.UUID) -> None:
        self._ensure_writable()

        obj = self.repo.get_one(obj_id)
        if obj is None:
            raise NotFoundError(f"{self.config.name} {obj_id} not found.")

        if self.config.check_delete:
            blockers = self.config.check_delete(obj, self.db)
            if blockers:
                raise ConflictError(
                    f"Cannot delete {self.config.name}: " + "; ".join(blockers),
                    details=[{"blockers": blockers}],
                )

        if self.config.hooks.before_delete:
            self.config.hooks.before_delete(obj, self.db, self.user)

        self._audit("delete", obj, changes={"before": self._snapshot(obj)})
        self.repo.soft_delete(obj)

        if self.config.hooks.after_delete:
            self.config.hooks.after_delete(obj, self.db, self.user)

    def restore(self, obj_id: uuid.UUID) -> BaseModel:
        self._ensure_writable()

        obj = self.repo.get_one(obj_id, include_deleted=True)
        if obj is None:
            raise NotFoundError(f"{self.config.name} {obj_id} not found.")
        if getattr(obj, "deleted_at", None) is None:
            raise ConflictError(f"{self.config.name} {obj_id} is not deleted.")

        if self.config.hooks.before_restore:
            self.config.hooks.before_restore(obj, self.db, self.user)

        try:
            with self.db.begin_nested():
                obj.deleted_at = None  # type: ignore[attr-defined]
                self.db.flush()
        except IntegrityError as exc:
            raise ConflictError(self._integrity_message(exc))

        if self.config.hooks.after_restore:
            self.config.hooks.after_restore(obj, self.db, self.user)

        self._audit("restore", obj, changes=None)
        return self._serialize(obj)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _ensure_writable(self) -> None:
        if self.config.read_only:
            raise ValidationFailedError(f"{self.config.name} is read-only.")

    def _serialize(self, obj: Any) -> BaseModel:
        source: Any = self.config.row_mapper(obj) if self.config.row_mapper else obj
        return self.config.read_schema.model_validate(source, from_attributes=True)

    def _snapshot(self, obj: Any) -> dict[str, Any]:
        exclude = _SENSITIVE_FIELDS | self.config.audit_exclude
        mapper = inspect(obj).mapper
        snapshot: dict[str, Any] = {}
        for attr in mapper.column_attrs:
            key = attr.key
            if key in exclude:
                continue
            value = getattr(obj, key)
            if isinstance(value, uuid.UUID):
                value = str(value)
            elif isinstance(value, datetime):
                value = value.isoformat()
            snapshot[key] = value
        return snapshot

    @staticmethod
    def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        for key, new_value in after.items():
            old_value = before.get(key)
            if old_value != new_value:
                changes[key] = {"before": old_value, "after": new_value}
        return changes

    def _audit(
        self,
        action: str,
        obj: Any,
        *,
        changes: dict[str, Any] | None,
    ) -> None:
        writer = self.config.audit_writer
        if writer is None:
            return
        writer(
            db=self.db,
            user=self.user,
            action=action,
            resource=self.config.name,
            record_id=getattr(obj, "id", None),
            changes=changes,
        )

    @staticmethod
    def _integrity_message(exc: IntegrityError) -> str:
        raw = str(getattr(exc, "orig", exc))
        return f"Constraint violation: {raw}"


__all__ = [
    "Hooks",
    "ResourceConfig",
    "CrudRepository",
    "CrudService",
]