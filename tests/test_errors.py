"""Standard error envelope for validation failures on a real Phase 3 endpoint."""

from __future__ import annotations


def test_validation_error_returns_standard_envelope(client):
    # Missing "password" -> Pydantic 422 with the standard envelope.
    resp = client.post("/api/v1/auth/login", json={"username": "x"})
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert "error" in body
    err = body["error"]
    assert err["code"] == "VALIDATION_FAILED"
    assert isinstance(err["message"], str)
    assert isinstance(err["details"], list)
    assert isinstance(err["request_id"], str)
    assert resp.headers["X-Request-ID"] == err["request_id"]


def test_404_returns_standard_envelope(client):
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert isinstance(err["request_id"], str)


def test_401_has_www_authenticate_header(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"
