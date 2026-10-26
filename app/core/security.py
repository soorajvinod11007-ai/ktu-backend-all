"""Password hashing + JWT issuance/verification for Phase 3."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

# bcrypt has a 72-byte input limit; passlib truncates silently.
# bcrypt<4.1 avoids the passlib 1.7.4 `__about__` warning — pin in pyproject.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Precomputed hash used to burn CPU when a username does not exist, so
# /auth/login response time does not reveal which usernames are valid.
_DUMMY_HASH = pwd_context.hash("this-is-not-a-real-password")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def dummy_verify() -> None:
    """Run a bcrypt verify against a fixed dummy hash (timing equalization)."""
    pwd_context.verify("this-is-not-a-real-password", _DUMMY_HASH)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
TokenType = Literal["access", "refresh"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(payload: dict[str, Any]) -> str:
    settings = get_settings()
    return jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_access_token(*, user_id: uuid.UUID | str, role: str) -> tuple[str, datetime]:
    """Return (encoded_jwt, expires_at_utc)."""
    settings = get_settings()
    now = _now()
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return _encode(payload), expires_at


def create_refresh_token(
    *, user_id: uuid.UUID | str
) -> tuple[str, str, datetime, str]:
    """Return (raw_jwt, jti, expires_at_utc, token_hash)."""
    settings = get_settings()
    now = _now()
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": jti,
    }
    token = _encode(payload)
    return token, jti, expires_at, hash_refresh_token(token)


def hash_refresh_token(raw_token: str) -> str:
    """SHA-256 hex digest of the raw refresh-token string."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def decode_token(raw_token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a JWT. Raises UnauthorizedError on any failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            raw_token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "type", "jti"]},
        )
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token has expired.")
    except jwt.PyJWTError:
        raise UnauthorizedError("Invalid token.")

    if payload.get("type") != expected_type:
        # Reject access-as-refresh and refresh-as-access.
        raise UnauthorizedError("Invalid token type.")

    return payload


__all__ = [
    "hash_password",
    "verify_password",
    "pwd_context",
    "dummy_verify",
    "create_access_token",
    "create_refresh_token",
    "hash_refresh_token",
    "decode_token",
]