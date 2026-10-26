"""Populates request_ip_var / request_id_var for the current request."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.context import request_id_var, request_ip_var


class AuditContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client = request.client
        ip = client.host if client else None
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())

        ip_token = request_ip_var.set(ip)
        rid_token = request_id_var.set(rid)
        request.state.request_id = rid
        try:
            return await call_next(request)
        finally:
            request_ip_var.reset(ip_token)
            request_id_var.reset(rid_token)


__all__ = ["AuditContextMiddleware"]