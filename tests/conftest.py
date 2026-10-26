"""Shared pytest fixtures. Uses TEST_DATABASE_URL, not the dev DB."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.rate_limit import get_rate_limiter
from app.core.security import hash_password
from app.main import app
from app.modules.auth.models import RefreshToken, User, UserRole

settings = get_settings()

# ---------------------------------------------------------------------------
# Test database
# ---------------------------------------------------------------------------
# Fall back to TEST_DATABASE_URL; refuse to run against the dev DB.
TEST_DB_URL = settings.TEST_DATABASE_URL
assert "test" in TEST_DB_URL.lower(), (
    f"TEST_DATABASE_URL must point at a *_test database, got {TEST_DB_URL!r}"
)

is_sqlite = TEST_DB_URL.startswith("sqlite")
engine_kwargs: dict = {"future": True}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(TEST_DB_URL, **engine_kwargs)

if is_sqlite:
    from datetime import datetime, timezone
    from sqlalchemy import event
    import sqlalchemy as sa
    from sqlalchemy.dialects.sqlite.base import DATETIME

    class SQLiteDateTimeUTC(DATETIME):
        def result_processor(self, dialect, coltype):
            super_proc = super().result_processor(dialect, coltype)

            def process(value):
                res = super_proc(value) if super_proc else value
                if isinstance(res, datetime) and res.tzinfo is None:
                    return res.replace(tzinfo=timezone.utc)
                return res

            return process

    engine.dialect.colspecs[sa.DateTime] = SQLiteDateTimeUTC

    @event.listens_for(engine, "connect")
    def _set_test_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        try:
            dbapi_connection.create_function(
                "now", 0, lambda: datetime.now(timezone.utc).isoformat()
            )
        except Exception:
            pass

TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Iterator[None]:
    """Create tables once per session, drop them at the end.

    Uses create_all() so tests don't depend on Alembic state. If you'd rather
    run Alembic here, swap the body for `alembic upgrade head` via subprocess.
    """
    # Always rebuild from the current models so stale test DB files
    # (left over from a previous session) never cause schema mismatch errors
    # when columns are added.  Safe: we only ever touch the _test database.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # Dispose *all* pooled connections before dropping tables.
    # Without this, TestClient's lifespan event may keep a connection open
    # and SQLite raises "database table is locked" during drop_all.
    engine.dispose()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    """Truncate or delete every table between tests so tests are independent."""
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.execute(text("PRAGMA foreign_keys = OFF;"))
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
            conn.execute(text("PRAGMA foreign_keys = ON;"))
        else:
            # Order matters only if FKs are enforced; TRUNCATE ... CASCADE is safe.
            conn.execute(text("TRUNCATE TABLE refresh_tokens, users RESTART IDENTITY CASCADE"))
    # Reset the in-memory rate limiter so tests don't leak buckets into each other.
    limiter = get_rate_limiter()
    reset = getattr(limiter, "reset", None)
    if callable(reset):
        reset()
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """TestClient with get_db overridden to the test session."""

    def _get_db_override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User factories
# ---------------------------------------------------------------------------
def make_user(
    db: Session,
    *,
    username: str = "admin",
    password: str = "supersecret",
    email: str | None = None,
    role: UserRole = UserRole.ADMIN,
    is_active: bool = True,
    failed_login_count: int = 0,
    locked_until: datetime | None = None,
) -> User:
    user = User(
        username=username,
        email=email or f"{username}@example.com",
        hashed_password=hash_password(password),
        role=role,
        is_active=is_active,
        failed_login_count=failed_login_count,
        locked_until=locked_until,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_user(db: Session) -> User:
    return make_user(db, username="admin", role=UserRole.ADMIN)


@pytest.fixture
def principal_user(db: Session) -> User:
    return make_user(db, username="principal", role=UserRole.PRINCIPAL)


@pytest.fixture
def admin_token(client: TestClient, admin_user: User) -> str:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "supersecret"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def principal_token(client: TestClient, principal_user: User) -> str:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "principal", "password": "supersecret"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


__all__ = [
    "make_user",
    "auth_header",
]

# ---------------------------------------------------------------------------
# Phase 3 follow-up: tests that exercise the per-account lockout must
# bypass the per-IP rate limiter, since the rate-limit dependency runs
# before the service and would fire on request #6.
# ---------------------------------------------------------------------------
import pytest as _pytest  # noqa: E402


@_pytest.fixture
def no_rate_limit():
    from app.core.dependencies import rate_limit_login
    from app.main import app

    app.dependency_overrides[rate_limit_login] = lambda: None
    try:
        yield
    finally:
        app.dependency_overrides.pop(rate_limit_login, None)
