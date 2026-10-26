"""Pydantic v2 request/response schemas for the auth module."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.models import UserRole


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=72)


class UserSummary(BaseModel):
    """Trimmed user shape returned inside LoginResponse."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: UserRole


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserSummary


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------
class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------
class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


# ---------------------------------------------------------------------------
# Me
# ---------------------------------------------------------------------------
class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    role: UserRole


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------
class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    # Length policy (settings.PASSWORD_MIN_LENGTH) is enforced in the service
    # so the error carries our standard code and a useful message.
    new_password: str = Field(min_length=1, max_length=72)


__all__ = [
    "LoginRequest",
    "LoginResponse",
    "UserSummary",
    "RefreshRequest",
    "RefreshResponse",
    "LogoutRequest",
    "UserRead",
    "ChangePasswordRequest",
]