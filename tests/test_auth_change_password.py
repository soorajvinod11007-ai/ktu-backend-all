"""Change password — happy path, wrong current, session revocation."""

from __future__ import annotations

from tests.conftest import auth_header


def test_change_password_success_and_revokes_sessions(client, admin_user, admin_token):
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "supersecret"},
    ).json()

    r = client.post(
        "/api/v1/auth/change-password",
        headers=auth_header(admin_token),
        json={"current_password": "supersecret", "new_password": "brandnewpass1"},
    )
    assert r.status_code == 204

    # Old refresh token is now dead.
    r = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert r.status_code == 401

    # New password works for a fresh login.
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "brandnewpass1"},
    )
    assert r.status_code == 200

    # Old password no longer works.
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "supersecret"},
    )
    assert r.status_code == 401


def test_change_password_wrong_current(client, admin_user, admin_token):
    r = client.post(
        "/api/v1/auth/change-password",
        headers=auth_header(admin_token),
        json={"current_password": "wrong", "new_password": "brandnewpass1"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"


def test_change_password_same_as_current(client, admin_user, admin_token):
    r = client.post(
        "/api/v1/auth/change-password",
        headers=auth_header(admin_token),
        json={"current_password": "supersecret", "new_password": "supersecret"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"


def test_change_password_too_short(client, admin_user, admin_token):
    r = client.post(
        "/api/v1/auth/change-password",
        headers=auth_header(admin_token),
        json={"current_password": "supersecret", "new_password": "short"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"


def test_change_password_is_rate_limited(client, admin_user, admin_token):
    from app.core.rate_limit import get_rate_limiter

    get_rate_limiter().reset()
    codes = []
    for _ in range(6):
        r = client.post(
            "/api/v1/auth/change-password",
            headers=auth_header(admin_token),
            json={"current_password": "wrong", "new_password": "brandnewpass1"},
        )
        codes.append(r.status_code)
    assert codes[:5] == [422] * 5
    assert codes[5] == 429