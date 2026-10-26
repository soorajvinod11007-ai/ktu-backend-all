"""Pagination primitives shared by every admin list endpoint.

Limits come from settings, never from call sites.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query

from app.core.config import get_settings


@dataclass(frozen=True)
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination_params(
    page: int = Query(1, ge=1, description="1-based page number."),
    page_size: int | None = Query(
        None,
        ge=1,
        description="Items per page. Defaults to ADMIN_PAGE_SIZE_DEFAULT; capped at ADMIN_PAGE_SIZE_MAX.",
    ),
) -> PageParams:
    settings = get_settings()
    default_size = int(getattr(settings, "ADMIN_PAGE_SIZE_DEFAULT", 25))
    max_size = int(getattr(settings, "ADMIN_PAGE_SIZE_MAX", 100))

    size = page_size if page_size is not None else default_size
    if size > max_size:
        size = max_size
    return PageParams(page=page, page_size=size)


__all__ = ["PageParams", "pagination_params"]