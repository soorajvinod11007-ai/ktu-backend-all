"""Refresh rotation, reuse detection, and type confusion."""

from __future__ import annotations

from tests.conftest import auth_header


def _login(client, username="admin", password="supersecret"):
    r = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_refresh_rotates_tokens(client, admin_user):
    first = _login(client)
    r = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["access_token"]
    assert second["refresh_token"]
    assert second["refresh_token"] != first["refresh_token"]

    # New access token works.
    r = client.get("/api/v1/auth/me", headers=auth_header(second["access_token"]))
    assert r.status_code == 200


def test_reusing_old_refresh_revokes_whole_family(client, db, admin_user):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from app.core.security import hash_refresh_token
    from app.modules.auth.models import RefreshToken

    first = _login(client)
    rotated = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    ).json()

    # Move the revocation timestamp beyond the grace window (>10s ago)
    h = hash_refresh_token(first["refresh_token"])
    row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == h)).scalar_one()
    row.revoked_at = datetime.now(timezone.utc) - timedelta(seconds=20)
    db.commit()

    # Reuse the first token outside the grace window → 401 and family revoked.
    r = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"

    # The rotated token must now also be dead.
    r = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated["refresh_token"]},
    )
    assert r.status_code == 401


def test_access_token_rejected_as_refresh(client, admin_user, admin_token):
    r = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": admin_token},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_logout_revokes_refresh_token(client, admin_user):
    first = _login(client)
    r = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": first["refresh_token"]},
    )
    assert r.status_code == 204

    r = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert r.status_code == 401


def test_logout_unknown_token_still_204(client):
    r = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "not-a-real-token"},
    )
    assert r.status_code == 204


def test_refresh_race_condition_within_grace_window(client, admin_user):
    first = _login(client)
    r1 = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert r1.status_code == 200
    rotated = r1.json()

    # Re-presenting first token within the grace window returns 401 without revoking family
    r2 = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "UNAUTHORIZED"

    # Rotated token must still work!
    r3 = client.get("/api/v1/auth/me", headers=auth_header(rotated["access_token"]))
    assert r3.status_code == 200


def test_concurrent_refresh_calls(client, admin_user):
    import concurrent.futures
    from app.core.database import get_db
    from tests.conftest import TestingSessionLocal
    from app.main import app

    def _threaded_get_db():
        session = TestingSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _threaded_get_db
    try:
        first = _login(client)

        def do_refresh():
            return client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": first["refresh_token"]},
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(do_refresh)
            f2 = executor.submit(do_refresh)
            res1 = f1.result()
            res2 = f2.result()

        statuses = sorted([res1.status_code, res2.status_code])
        # One succeeds (200) and the second gets 401 within grace window
        assert statuses == [200, 401]

        # The successful token works
        winner = res1.json() if res1.status_code == 200 else res2.json()
        r = client.get("/api/v1/auth/me", headers=auth_header(winner["access_token"]))
        assert r.status_code == 200
    finally:
        pass