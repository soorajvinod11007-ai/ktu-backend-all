"""Filter validation + query-param coercion for the admin CRUD framework.

Only whitelisted filter fields are accepted. Values are coerced to the
column's Python type so the client gets a clean 422 instead of an opaque
database error. Queries are never built from raw user input.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import ColumnElement

from app.core.exceptions import ValidationFailedError


_TRUE = {"1", "true", "yes", "y", "on"}
_FALSE = {"0", "false", "no", "n", "off"}


def coerce_filter_value(column: ColumnElement, raw: str) -> Any:
    """Convert a raw query-string value into the column's Python type."""
    try:
        py_type = column.type.python_type  # type: ignore[union-attr]
    except (AttributeError, NotImplementedError):
        return raw

    if py_type is str or py_type is None:
        return raw

    if py_type is bool:
        lowered = raw.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        raise ValidationFailedError(
            f"Invalid boolean value for filter: {raw!r}",
            details=[{"value": raw}],
        )

    if py_type is uuid.UUID:
        try:
            return uuid.UUID(raw)
        except (ValueError, TypeError):
            raise ValidationFailedError(
                f"Invalid UUID value for filter: {raw!r}",
                details=[{"value": raw}],
            )

    if isinstance(py_type, type) and issubclass(py_type, enum.Enum):
        try:
            return py_type(raw)
        except ValueError:
            allowed = [m.value for m in py_type]
            raise ValidationFailedError(
                f"Invalid value {raw!r}. Allowed: {allowed}",
                details=[{"value": raw, "allowed": allowed}],
            )

    if py_type is int:
        try:
            return int(raw)
        except (ValueError, TypeError):
            raise ValidationFailedError(
                f"Invalid integer value for filter: {raw!r}",
                details=[{"value": raw}],
            )

    if py_type is float:
        try:
            return float(raw)
        except (ValueError, TypeError):
            raise ValidationFailedError(
                f"Invalid float value for filter: {raw!r}",
                details=[{"value": raw}],
            )

    return raw


def parse_filters(
    raw: dict[str, str],
    allowed: dict[str, ColumnElement],
) -> dict[str, Any]:
    """Validate raw query-string filters against the resource whitelist."""
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in allowed:
            raise ValidationFailedError(
                f"Unknown filter field: {key}",
                details=[{"field": key, "allowed": sorted(allowed.keys())}],
            )
        if value is None or value == "":
            continue
        out[key] = coerce_filter_value(allowed[key], value)
    return out


__all__ = ["coerce_filter_value", "parse_filters"]