"""Sort validation for the admin CRUD framework.

Accepts a comma-separated list like ``-created_at,name``. Any field not
declared as sortable on the resource raises ``ValidationFailedError``.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement

from app.core.exceptions import ValidationFailedError


def parse_sort(
    raw: str | None,
    allowed: dict[str, ColumnElement],
    default: str,
) -> list:
    """Turn a sort token into a list of ORDER BY expressions."""
    token = (raw or default or "").strip()
    if not token:
        return []

    exprs: list = []
    for part in token.split(","):
        part = part.strip()
        if not part:
            continue

        descending = part.startswith("-")
        name = part.lstrip("+-").strip()

        if name not in allowed:
            raise ValidationFailedError(
                f"Unknown sort field: {name}",
                details=[{"field": name, "allowed": sorted(allowed.keys())}],
            )

        column = allowed[name]
        exprs.append(column.desc() if descending else column.asc())

    return exprs


__all__ = ["parse_sort"]