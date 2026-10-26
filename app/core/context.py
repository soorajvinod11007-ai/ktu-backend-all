"""Request-scoped context values used by the audit writer.

Set by AuditContextMiddleware, read by app.modules.audit.service. Kept
tiny and dependency-free so nothing imports FastAPI just to read an IP.
"""

from __future__ import annotations

from contextvars import ContextVar

request_ip_var: ContextVar[str | None] = ContextVar("request_ip", default=None)
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

__all__ = ["request_ip_var", "request_id_var"]