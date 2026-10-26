"""Data-access layer for users and refresh tokens. No business rules here."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.auth.models import RefreshToken, User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(
            User.username == username,
            User.deleted_at.is_(None),
        )
        return self.db.execute(stmt).scalar_one_or_none()


class RefreshTokenRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, token: RefreshToken) -> RefreshToken:
        self.db.add(token)
        self.db.flush()  # populate token.id for replaced_by_id
        return token

    def get_by_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> RefreshToken | None:
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.deleted_at.is_(None),
        )
        if for_update and self.db.bind and self.db.bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()
        return self.db.execute(stmt).scalar_one_or_none()

    def revoke(
        self, token: RefreshToken, *, replaced_by_id: uuid.UUID | None = None
    ) -> bool:
        if token.revoked_at is not None:
            return False
        now = datetime.now(timezone.utc)
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.id == token.id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now, replaced_by_id=replaced_by_id)
        )
        res = self.db.execute(stmt)
        if res.rowcount == 0:
            return False
        token.revoked_at = now
        token.replaced_by_id = replaced_by_id
        self.db.flush()
        return True

    def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        """Revoke every non-revoked refresh token owned by the user."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        self.db.execute(stmt)
        self.db.flush()


__all__ = ["UserRepository", "RefreshTokenRepository"]