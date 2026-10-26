"""Auth business rules: login, refresh (rotation + reuse detection), logout,
change-password. Never touches HTTP concerns and never logs secrets."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    AccountLockedError,
    UnauthorizedError,
    ValidationFailedError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    dummy_verify,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.repository import RefreshTokenRepository, UserRepository

logger = logging.getLogger(__name__)

# A single generic message prevents user/credential enumeration.
_INVALID_CREDENTIALS = "Invalid credentials"
_INVALID_REFRESH = "Invalid refresh token."


@dataclass(frozen=True)
class LoginResult:
    user: User
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True)
class RefreshResult:
    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.tokens = RefreshTokenRepository(db)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    def login(
        self,
        *,
        username: str,
        password: str,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> LoginResult:
        settings = get_settings()
        user = self.users.get_by_username(username)

        if user is None:
            # Burn bcrypt so response time does not reveal valid usernames.
            dummy_verify()
            raise UnauthorizedError(_INVALID_CREDENTIALS)

        now = datetime.now(timezone.utc)

        # Locked account: reject with 423 before touching the password so a
        # correct password cannot bypass the lockout.
        if user.locked_until is not None:
            locked_until = user.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until > now:
                raise AccountLockedError(
                    "Account is locked due to too many failed login attempts."
                )
            user.locked_until = None
            user.failed_login_count = 0

        if not verify_password(password, user.hashed_password):
            self._register_failed_attempt(user)
            self.db.commit()
            raise UnauthorizedError(_INVALID_CREDENTIALS)

        # Inactive accounts get the same generic 401 so we don't leak that
        # the credentials were actually valid.
        if not user.is_active:
            raise UnauthorizedError(_INVALID_CREDENTIALS)

        # Success — reset lockout state and record login time.
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now

        access_token, _ = create_access_token(
            user_id=user.id, role=user.role.value
        )
        refresh_raw, jti, refresh_exp, token_hash = create_refresh_token(
            user_id=user.id
        )
        self.tokens.add(
            RefreshToken(
                user_id=user.id,
                token_hash=token_hash,
                jti=jti,
                expires_at=refresh_exp,
                user_agent=user_agent,
                ip=ip,
            )
        )
        self.db.commit()

        return LoginResult(
            user=user,
            access_token=access_token,
            refresh_token=refresh_raw,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    def _register_failed_attempt(self, user: User) -> None:
        settings = get_settings()
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(
                minutes=settings.LOGIN_LOCKOUT_MINUTES
            )

    # ------------------------------------------------------------------
    # Refresh (rotation + reuse detection)
    # ------------------------------------------------------------------
    def refresh(
        self,
        *,
        refresh_token: str,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> RefreshResult:
        settings = get_settings()

        now = datetime.now(timezone.utc)
        # 1. Decode and confirm type=refresh (rejects access-as-refresh).
        payload = decode_token(refresh_token, expected_type="refresh")
        jti = str(payload.get("jti", ""))
        try:
            user_id = uuid.UUID(str(payload["sub"]))
        except (KeyError, ValueError, TypeError):
            raise UnauthorizedError(_INVALID_REFRESH)

        # 2. Look up the stored hash with row lock.
        stored = self.tokens.get_by_hash(
            hash_refresh_token(refresh_token), for_update=True
        )
        if stored is None or stored.jti != jti:
            raise UnauthorizedError(_INVALID_REFRESH)

        # 3. Load user (and require active).
        user = self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            # Kill the whole family — nothing should be able to refresh for
            # a user that is gone or deactivated.
            self.tokens.revoke_all_for_user(user_id)
            self.db.commit()
            raise UnauthorizedError(_INVALID_REFRESH)

        # 4. Reuse detection: a revoked token being presented again.
        # Allow short grace window for concurrent requests with replaced_by_id.
        if stored.revoked_at is not None:
            revoked_at = stored.revoked_at
            if revoked_at.tzinfo is None:
                revoked_at = revoked_at.replace(tzinfo=timezone.utc)
            grace_seconds = getattr(settings, "REFRESH_REUSE_GRACE_SECONDS", 10)
            if (
                stored.replaced_by_id is not None
                and (now - revoked_at).total_seconds() <= grace_seconds
            ):
                raise UnauthorizedError(_INVALID_REFRESH)

            logger.warning(
                "refresh_token_reuse_detected",
                extra={"user_id": str(user.id)},
            )
            self.tokens.revoke_all_for_user(user.id)
            self.db.commit()
            raise UnauthorizedError(_INVALID_REFRESH)

        # 5. Expired tokens (never rotated).
        expires_at = stored.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            self.tokens.revoke(stored)
            self.db.commit()
            raise UnauthorizedError(_INVALID_REFRESH)

        # 6. Rotate: issue new access + refresh, link the chain, revoke old.
        access_token, _ = create_access_token(
            user_id=user.id, role=user.role.value
        )
        new_raw, new_jti, new_exp, new_hash = create_refresh_token(user_id=user.id)
        new_row = self.tokens.add(
            RefreshToken(
                user_id=user.id,
                token_hash=new_hash,
                jti=new_jti,
                expires_at=new_exp,
                user_agent=user_agent,
                ip=ip,
            )
        )
        if not self.tokens.revoke(stored, replaced_by_id=new_row.id):
            self.db.rollback()
            raise UnauthorizedError(_INVALID_REFRESH)
        self.db.commit()

        return RefreshResult(
            access_token=access_token,
            refresh_token=new_raw,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------
    def logout(self, *, refresh_token: str) -> None:
        """Revoke the supplied refresh token. Unknown/invalid tokens are a
        no-op — the endpoint always returns 204."""
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except UnauthorizedError:
            return

        stored = self.tokens.get_by_hash(hash_refresh_token(refresh_token))
        if stored is None or stored.revoked_at is not None:
            return
        if stored.jti != str(payload.get("jti", "")):
            return

        self.tokens.revoke(stored)
        self.db.commit()

    # ------------------------------------------------------------------
    # Change password
    # ------------------------------------------------------------------
    def change_password(
        self,
        *,
        user: User,
        current_password: str,
        new_password: str,
    ) -> None:
        settings = get_settings()

        if not verify_password(current_password, user.hashed_password):
            raise ValidationFailedError(
                "Current password is incorrect.",
                details=[
                    {"field": "current_password", "message": "Incorrect password."}
                ],
            )

        if new_password == current_password:
            raise ValidationFailedError(
                "New password must differ from the current one.",
                details=[
                    {
                        "field": "new_password",
                        "message": "Password must be different.",
                    }
                ],
            )

        if len(new_password) < settings.PASSWORD_MIN_LENGTH:
            raise ValidationFailedError(
                f"New password must be at least {settings.PASSWORD_MIN_LENGTH} characters.",
                details=[{"field": "new_password", "message": "Too short."}],
            )

        user.hashed_password = hash_password(new_password)
        # All active sessions are logged out.
        self.tokens.revoke_all_for_user(user.id)
        self.db.commit()


__all__ = ["AuthService", "LoginResult", "RefreshResult"]