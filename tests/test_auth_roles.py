"""Role gating on a sample route: principal read-only, admin full."""

from __future__ import annotations

from tests.conftest import auth_header


def test_admin_can_read_and_write_reports(client, admin_user, admin_token):
    r = client.get("/api/v1/reports", headers=auth_header(admin_token))
    assert r.status_code == 200

    r = client.post("/api/v1/reports", headers=auth_header(admin_token))
    assert r.status_code == 201


def test_principal_can_read_but_not_write(client, principal_user, principal_token):
    r = client.get("/api/v1/reports", headers=auth_header(principal_token))
    assert r.status_code == 200

    r = client.post("/api/v1/reports", headers=auth_header(principal_token))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"


def test_unauthenticated_cannot_read_reports(client):
    r = client.get("/api/v1/reports")
    assert r.status_code == 401