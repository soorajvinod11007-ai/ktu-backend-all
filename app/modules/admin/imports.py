"""POST /admin/{resource}/import and .../import/{upload_id}/confirm.

Only students, faculty, and subjects are importable. Preview validates
every row through the resource's full create/update pipeline (inside a
rolled-back SAVEPOINT), records an upload_logs row with status
"preview", and saves nothing. Confirm re-plays the stored payload in a
single transaction and flips the row to "committed".

Assumes ``upload_logs.preview_payload`` (JSONB, nullable) and
``upload_logs.resource`` (String, nullable) — migration is in Part 4.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from typing import Any, Iterable

from fastapi import Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.crud import CrudService, ResourceConfig
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import (
    BaseAPIError,
    ConflictError,
    NotFoundError,
    ValidationFailedError,
)
from app.modules.admin.registry import ResourceConfig as _RC  # re-export for typing
from app.modules.auth.dependencies import require_admin

# Resources the framework will accept import files for.
IMPORTABLE_RESOURCES = frozenset({"students", "faculty", "subjects"})

# Natural key per importable resource — used to classify rows as
# create vs update and to detect soft-deleted duplicates.
NATURAL_KEYS: dict[str, str] = {
    "students": "register_no",
    "faculty": "email",
    "subjects": "code",
}


# --------------------------------------------------------------------------- #
# File parsing
# --------------------------------------------------------------------------- #
def _parse_csv(data: bytes) -> list[dict[str, Any]]:
    text = io.StringIO(data.decode("utf-8-sig"))
    reader = csv.DictReader(text)
    return [dict(row) for row in reader]


def _parse_xlsx(data: bytes) -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows)
    except StopIteration:
        return []
    headers = [(str(h).strip() if h is not None else "") for h in header_row]

    out: list[dict[str, Any]] = []
    for row in rows:
        if all(c is None or c == "" for c in row):
            continue
        out.append({headers[i]: row[i] for i in range(len(headers))})
    return out


def _read_upload(file: UploadFile, max_bytes: int) -> tuple[str, list[dict[str, Any]]]:
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValidationFailedError(
            f"Upload exceeds maximum size of {max_bytes} bytes.",
            details=[{"max_bytes": max_bytes, "received_at_least": len(data)}],
        )

    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "csv":
        rows = _parse_csv(data)
    elif ext in {"xlsx", "xlsm"}:
        rows = _parse_xlsx(data)
    else:
        raise ValidationFailedError(
            "Only .csv and .xlsx files are supported.",
            details=[{"filename": filename}],
        )
    return filename, rows


# --------------------------------------------------------------------------- #
# Preview
# --------------------------------------------------------------------------- #
def _classify_row(
    config: ResourceConfig,
    db: Session,
    user: Any,
    row_data: dict[str, Any],
) -> tuple[str, Any, dict[str, Any]]:
    """Return ``(action, existing_id, normalized_data)``.

    ``action`` is "create" or "update". Raises ``BaseAPIError`` on any
    business-rule failure (duplicate register_no, invalid FK, ...).
    """
    payload = config.create_schema.model_validate(row_data)
    explicit = payload.model_dump(exclude_unset=True, mode="python")
    full = payload.model_dump(mode="python")

    natural = NATURAL_KEYS[config.name]
    natural_column = getattr(config.model, natural)
    natural_value = full.get(natural)

    existing = db.execute(
        select(config.model).where(natural_column == natural_value)
    ).scalar_one_or_none()

    if existing is not None and getattr(existing, "deleted_at", None) is not None:
        raise ConflictError(
            f"Row matches soft-deleted {config.name} {existing.id}. "
            "Restore that record instead of re-importing.",
            details=[{"existing_id": str(existing.id), "deleted": True}],
        )

    if existing is not None:
        return "update", existing.id, explicit
    return "create", None, full


def _dry_run(
    config: ResourceConfig,
    db: Session,
    user: Any,
    action: str,
    existing_id: Any,
    data: dict[str, Any],
) -> None:
    """Run the full write path inside a SAVEPOINT we always roll back.

    Ensures hooks (register-no parsing, FK checks, duplicate detection)
    actually execute, without touching persisted state.
    """
    service = CrudService(config, db, user)
    sp = db.begin_nested()
    try:
        if action == "create":
            service.create(data)
        else:
            service.update(existing_id, data)
    except BaseAPIError:
        sp.rollback()
        raise
    except Exception:
        sp.rollback()
        raise
    else:
        sp.rollback()


def preview_import(
    config: ResourceConfig,
    db: Session,
    user: Any,
    file: UploadFile,
) -> dict[str, Any]:
    if config.name not in IMPORTABLE_RESOURCES:
        raise ValidationFailedError(
            f"Import is not supported for {config.name}.",
            details=[{"resource": config.name}],
        )

    settings = get_settings()
    max_bytes = int(getattr(settings, "ADMIN_IMPORT_MAX_BYTES", 10 * 1024 * 1024))
    filename, rows = _read_upload(file, max_bytes)

    valid: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    new_count = 0
    update_count = 0

    for idx, row_data in enumerate(rows, start=2):  # header occupies row 1
        try:
            action, existing_id, data = _classify_row(config, db, user, row_data)
            _dry_run(config, db, user, action, existing_id, data)
        except BaseAPIError as exc:
            errors.append(
                {
                    "row": idx,
                    "message": exc.message,
                    "details": exc.details,
                }
            )
            continue
        except Exception as exc:  # pydantic ValidationError already handled above
            errors.append({"row": idx, "message": str(exc), "details": None})
            continue

        if action == "create":
            new_count += 1
        else:
            update_count += 1

        # Store JSON-safe data so it survives the DB round-trip.
        stored = config.create_schema.model_validate(row_data).model_dump(mode="json")
        valid.append(
            {
                "row": idx,
                "action": action,
                "id": str(existing_id) if existing_id else None,
                "data": stored,
            }
        )

    # Persist the upload_logs record. This is the only write a preview makes.
    from app.modules.uploads.models import UploadLog  # type: ignore

    log = UploadLog(
        file_type=filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown",
        status="preview",
        filename=filename,
        resource=config.name,
        uploaded_by_user_id=getattr(user, "id", None),
        total_rows=len(rows),
        valid_rows=len(valid),
        error_rows=len(errors),
        preview_payload={
            "valid": valid,
            "errors": errors,
            "counts": {
                "new": new_count,
                "updates": update_count,
                "errors": len(errors),
                "total": len(rows),
            },
        },
    )
    db.add(log)
    db.flush()

    if config.audit_writer is not None:
        config.audit_writer(
            db=db,
            user=user,
            action="import",
            resource=config.name,
            record_id=log.id,
            changes={"step": "preview", "counts": log.preview_payload["counts"]},
        )

    return {
        "upload_id": str(log.id),
        "resource": config.name,
        "total_rows": len(rows),
        "valid_rows": len(valid),
        "error_rows": len(errors),
        "counts": {"new": new_count, "updates": update_count},
        "valid": valid,
        "errors": errors,
        "status": "preview",
    }


# --------------------------------------------------------------------------- #
# Confirm
# --------------------------------------------------------------------------- #
def confirm_import(
    config: ResourceConfig,
    db: Session,
    user: Any,
    upload_id: uuid.UUID,
) -> dict[str, Any]:
    if config.name not in IMPORTABLE_RESOURCES:
        raise ValidationFailedError(f"Import is not supported for {config.name}.")

    from app.modules.uploads.models import UploadLog  # type: ignore

    log = db.execute(
        select(UploadLog).where(
            UploadLog.id == upload_id,
            UploadLog.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if log is None:
        raise NotFoundError(f"Upload {upload_id} not found.")
    if getattr(log, "resource", None) != config.name:
        raise ConflictError(
            f"Upload {upload_id} belongs to resource {log.resource!r}, not {config.name!r}."
        )
    if log.status != "preview":
        raise ConflictError(
            f"Upload {upload_id} is in state {log.status!r}; nothing to confirm."
        )

    payload = log.preview_payload or {}
    valid: list[dict[str, Any]] = list(payload.get("valid") or [])

    service = CrudService(config, db, user)
    try:
        with db.begin_nested():
            for entry in valid:
                data = entry["data"]
                if entry["action"] == "create":
                    service.create(data)
                else:
                    service.update(uuid.UUID(entry["id"]), data)
    except BaseAPIError:
        raise  # outer transaction stays clean — nothing was written.

    log.status = "committed"
    db.flush()

    if config.audit_writer is not None:
        config.audit_writer(
            db=db,
            user=user,
            action="import",
            resource=config.name,
            record_id=log.id,
            changes={
                "step": "confirm",
                "applied": len(valid),
                "counts": payload.get("counts"),
            },
        )

    return {
        "upload_id": str(log.id),
        "resource": config.name,
        "applied": len(valid),
        "counts": payload.get("counts"),
        "status": "committed",
    }


__all__ = [
    "IMPORTABLE_RESOURCES",
    "NATURAL_KEYS",
    "preview_import",
    "confirm_import",
]