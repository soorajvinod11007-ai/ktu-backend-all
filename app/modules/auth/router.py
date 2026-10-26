"""Auth HTTP layer. Handlers only translate HTTP <-> service calls."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import rate_limit_login
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
    UserRead,
    UserSummary,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip, user_agent


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Exchange username + password for access and refresh tokens.",
    dependencies=[Depends(rate_limit_login)],
)
def login(
    payload: LoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    ip, user_agent = _client_meta(request)
    result = service.login(
        username=payload.username,
        password=payload.password,
        user_agent=user_agent,
        ip=ip,
    )
    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type="bearer",
        expires_in=result.expires_in,
        user=UserSummary.model_validate(result.user),
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Rotate a refresh token. The old token is invalidated.",
)
def refresh(
    payload: RefreshRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> RefreshResponse:
    ip, user_agent = _client_meta(request)
    result = service.refresh(
        refresh_token=payload.refresh_token,
        user_agent=user_agent,
        ip=ip,
    )
    return RefreshResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type="bearer",
        expires_in=result.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a refresh token. Always returns 204.",
)
def logout(
    payload: LogoutRequest,
    service: AuthService = Depends(get_auth_service),
) -> Response:
    service.logout(refresh_token=payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Return the current authenticated user.",
)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the current user's password and revoke all their sessions.",
    dependencies=[Depends(rate_limit_login)],
)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    service.change_password(
        user=current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]