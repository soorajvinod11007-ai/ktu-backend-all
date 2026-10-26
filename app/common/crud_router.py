"""Turns a ResourceConfig into an APIRouter.

Split out from ``crud.py`` so the ORM-facing framework stays free of
FastAPI imports.

Route ordering matters: ``/export`` and ``/import`` are declared BEFORE
``/{obj_id}`` because FastAPI resolves routes first-match-wins — a bare
``/{obj_id}`` would otherwise swallow ``/export`` and fail UUID parsing.

NOTE: this module deliberately does NOT use
``from __future__ import annotations``. The create/update body parameter
is annotated with a runtime class chosen per resource, and the annotation
must be a real object (not a string) for FastAPI to see it.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from pydantic import create_model
from sqlalchemy.orm import Session

from app.common.crud import CrudService, ResourceConfig
from app.common.pagination import PageParams, pagination_params
from app.core.database import get_db
from app.common.export import build_export_endpoint
from app.modules.admin.imports import IMPORTABLE_RESOURCES, confirm_import, preview_import
from app.modules.auth.dependencies import require_admin

RESERVED_QUERY_PARAMS = frozenset(
    {"page", "page_size", "search", "sort", "include_deleted"}
)


def _list_response_model(config: ResourceConfig):
    camel = "".join(part.capitalize() for part in config.name.replace("-", "_").split("_"))
    return create_model(
        f"{camel}ListResponse",
        items=(list[config.read_schema], ...),
        total=(int, ...),
        page=(int, ...),
        page_size=(int, ...),
    )


def _extract_filter_params(request: Request) -> dict[str, str]:
    return {
        key: value
        for key, value in request.query_params.items()
        if key not in RESERVED_QUERY_PARAMS
    }


def build_resource_router(config: ResourceConfig) -> APIRouter:
    router = APIRouter(prefix=f"/{config.name}", tags=[f"admin:{config.name}"])

    def get_service(
        db: Session = Depends(get_db),
        user: Any = Depends(require_admin),
    ) -> CrudService:
        return CrudService(config, db, user)

    list_model = _list_response_model(config)

    # -------------------------------------------------------------- reads
    @router.get("", response_model=list_model, summary=f"List {config.name}")
    def list_items(
        request: Request,
        params: PageParams = Depends(pagination_params),
        search: str | None = Query(None, description="Free-text search."),
        sort: str | None = Query(None, description="e.g. name or -created_at."),
        include_deleted: bool = Query(False),
        service: CrudService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.list(
            params=params,
            search=search,
            sort=sort,
            include_deleted=include_deleted,
            raw_filters=_extract_filter_params(request),
        )

    # -------------------------------------------------------------- export
    export_handler = build_export_endpoint(config)
    router.add_api_route(
        "/export",
        export_handler,
        methods=["GET"],
        summary=f"Export filtered {config.name} to xlsx",
    )

    # -------------------------------------------------------------- import
    if config.name in IMPORTABLE_RESOURCES:

        @router.post("/import", summary=f"Preview {config.name} import")
        def import_preview_route(
            file: UploadFile = File(...),
            service: CrudService = Depends(get_service),
        ) -> dict[str, Any]:
            return preview_import(config, service.db, service.user, file)

        @router.post(
            "/import/{upload_id}/confirm",
            summary=f"Confirm {config.name} import",
        )
        def import_confirm_route(
            upload_id: uuid.UUID,
            service: CrudService = Depends(get_service),
        ) -> dict[str, Any]:
            return confirm_import(config, service.db, service.user, upload_id)

    # -------------------------------------------------------------- detail
    @router.get(
        "/{obj_id}",
        response_model=config.read_schema,
        summary=f"Get one {config.name}",
    )
    def get_item(obj_id: uuid.UUID, service: CrudService = Depends(get_service)) -> Any:
        return service.get(obj_id)

    if config.read_only:
        return router

    # ------------------------------------------------------------- writes
    @router.post(
        "",
        response_model=config.read_schema,
        status_code=status.HTTP_201_CREATED,
        summary=f"Create {config.name}",
    )
    def create_item(
        payload: config.create_schema,  # type: ignore[valid-type]
        service: CrudService = Depends(get_service),
    ) -> Any:
        return service.create(payload.model_dump(exclude_unset=False, mode="python"))

    @router.patch(
        "/{obj_id}",
        response_model=config.read_schema,
        summary=f"Update {config.name} (partial)",
    )
    def update_item(
        obj_id: uuid.UUID,
        payload: config.update_schema,  # type: ignore[valid-type]
        service: CrudService = Depends(get_service),
    ) -> Any:
        return service.update(obj_id, payload.model_dump(exclude_unset=True, mode="python"))

    @router.delete(
        "/{obj_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary=f"Soft-delete {config.name}",
    )
    def delete_item(obj_id: uuid.UUID, service: CrudService = Depends(get_service)) -> None:
        service.delete(obj_id)

    @router.post(
        "/{obj_id}/restore",
        response_model=config.read_schema,
        summary=f"Restore {config.name}",
    )
    def restore_item(obj_id: uuid.UUID, service: CrudService = Depends(get_service)) -> Any:
        return service.restore(obj_id)

    return router


__all__ = ["build_resource_router", "RESERVED_QUERY_PARAMS"]