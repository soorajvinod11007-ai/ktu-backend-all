"""Custom exceptions and global handlers producing the standard error envelope:

    {"error": {"code": str, "message": str, "details": list | null, "request_id": str}}
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# Starlette renamed this constant; fall back for older versions.
HTTP_422 = 422


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class BaseAPIError(Exception):
    """Base for all application errors."""

    code: str = "internal_error"
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[Any] | None = None,
        code: str | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        self.details = details
        super().__init__(self.message)


class NotFoundError(BaseAPIError):
    code = "NOT_FOUND"
    http_status = status.HTTP_404_NOT_FOUND
    message = "Resource not found."


class DuplicateError(BaseAPIError):
    code = "DUPLICATE"
    http_status = status.HTTP_409_CONFLICT
    message = "Resource already exists."


class ValidationFailedError(BaseAPIError):
    code = "VALIDATION_FAILED"
    http_status = HTTP_422
    message = "Validation failed."


class PermissionDeniedError(BaseAPIError):
    code = "PERMISSION_DENIED"
    http_status = status.HTTP_403_FORBIDDEN
    message = "Permission denied."


class ConflictError(BaseAPIError):
    code = "CONFLICT"
    http_status = status.HTTP_409_CONFLICT
    message = "Conflict with current state."


class ParseError(BaseAPIError):
    """Raised when a PDF/CSV parser hits a malformed row. Phase 4+ uses this."""

    code = "PARSE_ERROR"
    http_status = HTTP_422
    message = "Failed to parse document."

    def __init__(
        self,
        message: str | None = None,
        *,
        page: int | None = None,
        row: int | None = None,
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.page = page
        self.row = row

    def to_details(self) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {}
        if self.page is not None:
            payload["page"] = self.page
        if self.row is not None:
            payload["row"] = self.row
        return [payload] if payload else []
    

class UnauthorizedError(BaseAPIError):
    code = "UNAUTHORIZED"
    http_status = status.HTTP_401_UNAUTHORIZED
    message = "Unauthorized."

    # 401s must carry the WWW-Authenticate header per RFC 7235.
    headers = {"WWW-Authenticate": "Bearer"}


class AccountLockedError(BaseAPIError):
    code = "ACCOUNT_LOCKED"
    http_status = 423
    message = "Account is locked."


class TooManyRequestsError(BaseAPIError):
    code = "RATE_LIMITED"
    http_status = status.HTTP_429_TOO_MANY_REQUESTS
    message = "Too many requests."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[Any] | None = None,
        code: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message, details=details, code=code)
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _request_id(request: Request) -> str:
    """Pull request_id from state if the middleware set it; otherwise mint one."""
    rid = getattr(request.state, "request_id", None)
    if rid is None:
        rid = str(uuid.uuid4())
        request.state.request_id = rid
    return rid


def _envelope(
    *,
    code: str,
    message: str,
    details: list[Any] | None,
    request_id: str,
    http_status: int,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": request_id,
            }
        },
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
async def api_error_handler(request: Request, exc: BaseAPIError) -> JSONResponse:
    details = exc.details
    if isinstance(exc, ParseError) and details is None:
        details = exc.to_details()

    # Start empty; collect any headers the exception class wants to attach
    # (e.g. WWW-Authenticate on 401), plus Retry-After when present.
    headers: dict[str, str] = {}
    headers.update(getattr(exc, "headers", {}) or {})

    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    logger.warning(
        "api_error",
        extra={
            "code": exc.code,
            "path": request.url.path,
            "status": exc.http_status,
        },
    )
    return _envelope(
        code=exc.code,
        message=exc.message,
        details=details,
        request_id=_request_id(request),
        http_status=exc.http_status,
        headers=headers or None,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "PERMISSION_DENIED",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_FAILED",
    }.get(exc.status_code, "HTTP_ERROR")

    return _envelope(
        code=code,
        message=str(exc.detail),
        details=None,
        request_id=_request_id(request),
        http_status=exc.status_code,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details: list[dict[str, Any]] = []
    for err in exc.errors():
        details.append(
            {
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )

    return _envelope(
        code="VALIDATION_FAILED",
        message="Request validation failed.",
        details=details,
        request_id=_request_id(request),
        http_status=HTTP_422,
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("unhandled_exception", extra={"path": request.url.path})
    return _envelope(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred.",
        details=None,
        request_id=_request_id(request),
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BaseAPIError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


__all__ = [
    "BaseAPIError",
    "NotFoundError",
    "DuplicateError",
    "ValidationFailedError",
    "PermissionDeniedError",
    "ConflictError",
    "ParseError",
    "register_exception_handlers",
    "UnauthorizedError",
    "AccountLockedError",
    "TooManyRequestsError",
]