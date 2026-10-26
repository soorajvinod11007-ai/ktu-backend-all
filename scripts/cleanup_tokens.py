"""Cleanup expired and revoked refresh tokens older than REFRESH_TOKEN_RETENTION_DAYS."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.modules.auth.models import RefreshToken


def main(db: Session | None = None) -> int:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.REFRESH_TOKEN_RETENTION_DAYS)

    # If running inside pytest with a test database fixture
    if db is None:
        if "tests.conftest" in sys.modules:
            test_factory = getattr(sys.modules["tests.conftest"], "TestingSessionLocal", None)
            session_factory = test_factory or SessionLocal
        else:
            session_factory = SessionLocal
        session = session_factory()
        should_close = True
    else:
        session = db
        should_close = False

    try:
        stmt = delete(RefreshToken).where(
            or_(
                RefreshToken.expires_at < cutoff,
                RefreshToken.revoked_at < cutoff,
            )
        )
        res = session.execute(stmt)
        session.commit()
        return res.rowcount or 0
    finally:
        if should_close:
            session.close()


if __name__ == "__main__":
    count = main()
    print(f"Cleaned up {count} expired/revoked refresh tokens.")
