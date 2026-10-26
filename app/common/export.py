"""GET /admin/{resource}/export — streamed, injection-safe xlsx."""

from __future__ import annotations

import uuid

from fastapi import Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.crud import CrudService
from app.common.excel import XLSX_MEDIA_TYPE, build_xlsx
from app.core.database import get_db
from app.modules.admin.registry import ResourceConfig
from app.modules.auth.dependencies import require_admin


def build_export_endpoint(config: ResourceConfig):
    """Return a handler closing over ``config``.

    Declared before ``/{obj_id}`` so FastAPI's first-match-wins router
    does not interpret ``export`` as a UUID.
    """

    def export_items(
        request: Request,
        db: Session = Depends(get_db),
        user=Depends(require_admin),
    ) -> StreamingResponse:
        # Reuse the exact list filter set: everything on the query string
        # except the reserved pagination keys.
        from app.common.crud_router import RESERVED_QUERY_PARAMS

        raw_filters = {
            k: v
            for k, v in request.query_params.items()
            if k not in RESERVED_QUERY_PARAMS
        }
        search = request.query_params.get("search")
        sort = request.query_params.get("sort")
        include_deleted = request.query_params.get("include_deleted", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        service = CrudService(config, db, user)
        headers, rows = service.export_rows(
            include_deleted=include_deleted,
            search=search,
            sort=sort,
            raw_filters=raw_filters,
        )
        buf = build_xlsx(headers, rows)

        # Audit the export in the same transaction as anything else the
        # request may have done (there is nothing else here, but the
        # contract stays uniform).
        if config.audit_writer is not None:
            config.audit_writer(
                db=db,
                user=user,
                action="export",
                resource=config.name,
                record_id=None,
                changes={"filters": raw_filters, "search": search},
            )

        filename = f"{config.name}-export-{uuid.uuid4().hex[:8]}.xlsx"
        return StreamingResponse(
            buf,
            media_type=XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return export_items


__all__ = ["build_export_endpoint"]