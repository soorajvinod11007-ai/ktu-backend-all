"""/auth/me — happy path and every 401 flavor."""

from __future__ import annotations

import uuid
from datetime import timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token
from tests.conftest import auth_header

settings = get_settings()


def test_me_with_valid_access_token(client, admin_user, admin_token):
    r = client.get("/api/v1/auth/me", headers=auth_header(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(admin_user.id)
    assert body["username"] == "admin"
    assert body["email"] == "admin@example.com"
    assert body["role"] == "admin"


def test_me_without_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
    assert r.headers["www-authenticate"] == "Bearer"


def test_me_with_expired_token(client, admin_user):
    # Build an access token and back-date its exp.
    token, _ = create_access_token(user_id=admin_user.id, role="admin")
    payload = jwt.decode(
        token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
    )
    payload["exp"] = int((__import__("datetime").datetime.now(
        __import__("datetime").timezone.utc) - timedelta(seconds=10)).timestamp())
    expired = jwt.encode(
        payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    r = client.get("/api/v1/auth/me", headers=auth_header(expired))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_with_refresh_token_used_as_access(client, admin_user):
    raw, *_ = create_refresh_token(user_id=admin_user.id)
    r = client.get("/api/v1/auth/me", headers=auth_header(raw))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_with_tampered_token(client, admin_token):
    # Flip one character in the middle of the JWT signature.
    parts = admin_token.split(".")
    parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    tampered = ".".join(parts)
    r = client.get("/api/v1/auth/me", headers=auth_header(tampered))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"