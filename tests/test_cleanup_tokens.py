"""The cleanup script removes only expired / revoked tokens older than
the retention window."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.modules.auth.models import RefreshToken


def test_cleanup_deletes_old_tokens(db):
    now = datetime.now(timezone.utc)
    # Old, expired, still present.
    old = RefreshToken(
        user_id=uuid.uuid4(),
        token_hash="a" * 64,
        jti="old-expired",
        expires_at=now - timedelta(days=60),
    )
    # Recently revoked — should be kept (< retention).
    recent = RefreshToken(
        user_id=uuid.uuid4(),
        token_hash="b" * 64,
        jti="recent-revoked",
        expires_at=now + timedelta(days=1),
        revoked_at=now - timedelta(days=1),
    )
    # Active — must be kept.
    active = RefreshToken(
        user_id=uuid.uuid4(),
        token_hash="c" * 64,
        jti="active",
        expires_at=now + timedelta(days=1),
    )
    db.add_all([old, recent, active])
    db.commit()

    from scripts.cleanup_tokens import main as cleanup_main  # noqa: PLC0415

    cleanup_main()

    remaining = {row.jti for row in db.execute(select(RefreshToken)).scalars()}
    assert "old-expired" not in remaining
    assert "recent-revoked" in remaining
    assert "active" in remaining