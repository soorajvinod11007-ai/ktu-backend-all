"""Shared xlsx helpers: streaming writer and CSV/Excel injection guard."""

from __future__ import annotations

import enum
import io
import uuid
from datetime import date, datetime
from typing import Any, Iterable, Iterator, Sequence

from openpyxl import Workbook

# Excel treats a leading = + - @ as the start of a formula. Any string
# beginning with one of these is prefixed with a single quote so the cell
# is rendered literally by Excel and by any downstream CSV consumer.
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def sanitize_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        # openpyxl rejects timezone-aware datetime objects.
        # Strip tzinfo (value is already in UTC from the DB layer).
        return value.replace(tzinfo=None) if value.tzinfo is not None else value
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value and value[0] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def build_xlsx(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> io.BytesIO:
    """Return a BytesIO holding the full workbook.

    ``write_only=True`` keeps memory bounded — openpyxl flushes rows to disk
    as they are appended instead of retaining the whole worksheet object
    graph. The row cap is enforced upstream (see CrudService.export_rows).
    """
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("data")
    ws.append(list(headers))
    for row in rows:
        ws.append([sanitize_cell(v) for v in row])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


__all__ = ["sanitize_cell", "build_xlsx", "XLSX_MEDIA_TYPE"]