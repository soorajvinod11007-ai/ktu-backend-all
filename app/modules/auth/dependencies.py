"""FastAPI dependencies: current-user resolution and role gating.

Usage on any router:

    from app.modules.auth.dependencies import (
        get_current_user,
        require_admin,
        require_admin_or_principal,
    )

    # read-only — both roles
    @router.get("/reports", dependencies=[Depends(require_admin_or_principal)])
    def list_reports() -> ...: ...

    # admin only
    @router.post("/students", dependencies=[Depends(require_admin)])
    def create_student() -> ...: ...

    # when the handler needs the user object itself
    @router.get("/me/anything")
    def handler(user: User = Depends(get_current_user)) -> ...: ...
"""

from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import PermissionDeniedError, UnauthorizedError
from app.core.security import decode_token
from app.modules.auth.models import User, UserRole
from app.modules.auth.repository import UserRepository

# auto_error=False so we emit our own envelope instead of FastAPI's default.
# Registering an HTTPBearer scheme also enables the "Authorize" button in /docs.
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Missing authentication token.")

    # decode_token raises UnauthorizedError for expired / malformed /
    # wrong-type tokens; we let it propagate.
    payload = decode_token(credentials.credentials, expected_type="access")

    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError, TypeError):
        raise UnauthorizedError("Invalid token.")

    user = UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid or inactive user.")

    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    """Return a dependency that allows only the given roles."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise PermissionDeniedError(
                "You do not have permission to perform this action."
            )
        return user

    return dependency


# Ready-made shortcuts for the two roles defined today.
require_admin = require_roles(UserRole.ADMIN)
require_admin_or_principal = require_roles(UserRole.ADMIN, UserRole.PRINCIPAL)


__all__ = [
    "bearer_scheme",
    "get_current_user",
    "require_roles",
    "require_admin",
    "require_admin_or_principal",
]