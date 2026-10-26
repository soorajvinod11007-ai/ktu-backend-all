"""Login success / failure / lockout / rate limit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.conftest import make_user  # noqa: F401  (used by inactive-user test)


def test_login_success_returns_tokens_and_role(client, admin_user):
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "supersecret"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0
    assert body["user"] == {
        "id": str(admin_user.id),
        "username": "admin",
        "role": "admin",
    }


def test_wrong_password_and_unknown_username_return_identical_body(client, admin_user):
    wrong = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "nope"},
    )
    unknown = client.post(
        "/api/v1/auth/login",
        json={"username": "ghost", "password": "nope"},
    )
    assert wrong.status_code == 401
    assert unknown.status_code == 401

    for body in (wrong.json(), unknown.json()):
        assert body["error"]["code"] == "UNAUTHORIZED"
        assert body["error"]["message"] == "Invalid credentials"
        assert body["error"]["details"] is None
    assert wrong.headers["www-authenticate"] == "Bearer"
    assert unknown.headers["www-authenticate"] == "Bearer"


def test_inactive_user_cannot_log_in(client, db):
    make_user(db, username="frozen", password="supersecret", is_active=False)
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "frozen", "password": "supersecret"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Invalid credentials"


def test_five_wrong_passwords_lock_account(client, admin_user, no_rate_limit):
    """Per-account lockout. Rate limiter is disabled so we can reach the
    lockout path without the per-IP limiter firing first."""
    for _ in range(5):
        r = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "bad"},
        )
        assert r.status_code == 401

    # Correct password rejected while locked.
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "supersecret"},
    )
    assert r.status_code == 423, r.text
    assert r.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_lock_expires_and_login_works_again(client, db, admin_user, no_rate_limit):
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "bad"},
        )

    admin_user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.add(admin_user)
    db.commit()

    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "supersecret"},
    )
    assert r.status_code == 200, r.text


def test_lock_expires_and_single_bad_password_does_not_relock(client, db, admin_user, no_rate_limit):
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "bad"},
        )

    admin_user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.add(admin_user)
    db.commit()

    # Next single bad password should return 401 UNAUTHORIZED, NOT 423 ACCOUNT_LOCKED
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "bad"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_rate_limit_returns_429_on_sixth_attempt(client, admin_user):
    codes = []
    for _ in range(6):
        r = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "bad"},
        )
        codes.append(r.status_code)
    assert codes[:5] == [401] * 5
    assert codes[5] == 429

    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "bad"},
    )
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert "retry-after" in {k.lower() for k in r.headers.keys()}
