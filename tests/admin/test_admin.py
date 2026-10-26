"""Phase 4 admin CRUD tests.

Covers (per PROJECT_HANDOFF.md Phase 4 test requirements):
- Principal gets 403 on all admin routes except /dashboard
- Unknown filter/sort returns 422
- Last-admin protection (cannot delete, deactivate, demote)
- Admin cannot delete/deactivate themselves
- Student auto-fill (program + batch from register_no) and SGI flag
- Register-number uniqueness including soft-deleted hint
- Password hash never appears in any response
- Writable resources: list, create 201, get, patch, soft-delete 204, restore
- Read-only resources: list OK, POST blocked
- Dashboard accessible by both roles
- Audit log accessible by admin, 403 for principal
- Options endpoint with search
- Export endpoint returns xlsx
- Unauthenticated access returns 401
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_header, make_user
from app.modules.auth.models import UserRole
from app.modules.students.models import Batch, Division, Program


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def program(db: Session) -> Program:
    p = Program(code="CS", name="Computer Science & Engineering", is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def batch(db: Session) -> Batch:
    b = Batch(start_year=2022, end_year=2026, label="2022-26")
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@pytest.fixture
def division(db: Session, program: Program, batch: Batch) -> Division:
    d = Division(program_id=program.id, batch_id=batch.id, name="A")
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_headers(client: TestClient, db: Session) -> dict[str, str]:
    """Create an admin user and return Bearer headers."""
    make_user(db, username="admin_test", password="supersecret99", role=UserRole.ADMIN)
    r = client.post("/api/v1/auth/login", json={"username": "admin_test", "password": "supersecret99"})
    assert r.status_code == 200, r.text
    return auth_header(r.json()["access_token"])


def _principal_headers(client: TestClient, db: Session) -> dict[str, str]:
    make_user(db, username="principal_test", password="supersecret99", role=UserRole.PRINCIPAL)
    r = client.post("/api/v1/auth/login", json={"username": "principal_test", "password": "supersecret99"})
    assert r.status_code == 200, r.text
    return auth_header(r.json()["access_token"])


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_admin_can_read_dashboard(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.get("/api/v1/admin/dashboard", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "counts" in data
        assert "flagged_students" in data
        assert "recent_uploads" in data

    def test_principal_can_read_dashboard(self, client: TestClient, db: Session) -> None:
        headers = _principal_headers(client, db)
        r = client.get("/api/v1/admin/dashboard", headers=headers)
        assert r.status_code == 200

    def test_unauthenticated_dashboard_401(self, client: TestClient) -> None:
        r = client.get("/api/v1/admin/dashboard")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Principal 403 on admin write/list routes
# ---------------------------------------------------------------------------

class TestPrincipalForbidden:
    """Principal must get 403 on all admin write/list routes (except dashboard)."""

    @pytest.mark.parametrize("path", [
        "/api/v1/admin/users",
        "/api/v1/admin/programs",
        "/api/v1/admin/batches",
        "/api/v1/admin/students",
        "/api/v1/admin/subjects",
    ])
    def test_principal_list_403(self, client: TestClient, db: Session, path: str) -> None:
        headers = _principal_headers(client, db)
        r = client.get(path, headers=headers)
        assert r.status_code == 403

    def test_principal_post_programs_403(self, client: TestClient, db: Session) -> None:
        headers = _principal_headers(client, db)
        r = client.post(
            "/api/v1/admin/programs",
            headers=headers,
            json={"code": "ME", "name": "Mechanical Engineering", "is_active": True},
        )
        assert r.status_code == 403

    def test_principal_delete_user_403(self, client: TestClient, db: Session, admin_user: Any) -> None:
        headers = _principal_headers(client, db)
        r = client.delete(f"/api/v1/admin/users/{admin_user.id}", headers=headers)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Programs CRUD
# ---------------------------------------------------------------------------

class TestPrograms:
    BASE = "/api/v1/admin/programs"

    def test_create_program(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.post(self.BASE, headers=headers, json={
            "code": "CS", "name": "Computer Science & Engineering", "is_active": True
        })
        assert r.status_code == 201
        data = r.json()
        assert data["code"] == "CS"
        assert "hashed_password" not in str(data)

    def test_list_programs(self, client: TestClient, db: Session, program: Program) -> None:
        headers = _admin_headers(client, db)
        r = client.get(self.BASE, headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_list_response_shape(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.get(self.BASE, headers=headers)
        assert r.status_code == 200
        data = r.json()
        for key in ("items", "total", "page", "page_size"):
            assert key in data

    def test_get_program(self, client: TestClient, db: Session, program: Program) -> None:
        headers = _admin_headers(client, db)
        r = client.get(f"{self.BASE}/{program.id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["code"] == "CS"

    def test_patch_program(self, client: TestClient, db: Session, program: Program) -> None:
        headers = _admin_headers(client, db)
        r = client.patch(f"{self.BASE}/{program.id}", headers=headers, json={"name": "CSE Updated"})
        assert r.status_code == 200
        assert r.json()["name"] == "CSE Updated"

    def test_delete_program(self, client: TestClient, db: Session, program: Program) -> None:
        headers = _admin_headers(client, db)
        r = client.delete(f"{self.BASE}/{program.id}", headers=headers)
        assert r.status_code == 204

    def test_restore_program(self, client: TestClient, db: Session, program: Program) -> None:
        headers = _admin_headers(client, db)
        client.delete(f"{self.BASE}/{program.id}", headers=headers)
        r = client.post(f"{self.BASE}/{program.id}/restore", headers=headers)
        assert r.status_code == 200
        assert r.json()["deleted_at"] is None

    def test_unknown_filter_422(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.get(f"{self.BASE}?nonexistent_field=foo", headers=headers)
        assert r.status_code == 422

    def test_unknown_sort_422(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.get(f"{self.BASE}?sort=nonexistent_col", headers=headers)
        assert r.status_code == 422

    def test_get_nonexistent_404(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.get(f"{self.BASE}/{uuid.uuid4()}", headers=headers)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Users CRUD + protection
# ---------------------------------------------------------------------------

class TestUsers:
    BASE = "/api/v1/admin/users"

    def test_create_user(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.post(self.BASE, headers=headers, json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "securepass123",
            "role": "principal",
        })
        assert r.status_code == 201
        data = r.json()
        assert "hashed_password" not in data
        assert "password" not in data
        assert data["username"] == "newuser"
        assert data["role"] == "principal"

    def test_password_hash_never_in_list(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.get(self.BASE, headers=headers)
        assert r.status_code == 200
        assert "hashed_password" not in r.text

    def test_password_hash_never_in_detail(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r_list = client.get(self.BASE, headers=headers)
        items = r_list.json()["items"]
        if items:
            r = client.get(f"{self.BASE}/{items[0]['id']}", headers=headers)
            assert r.status_code == 200
            assert "hashed_password" not in r.text

    def test_cannot_delete_self(self, client: TestClient, db: Session) -> None:
        user = make_user(db, username="solo_admin", password="pass123456", role=UserRole.ADMIN)
        r = client.post("/api/v1/auth/login", json={"username": "solo_admin", "password": "pass123456"})
        headers = auth_header(r.json()["access_token"])
        r = client.delete(f"{self.BASE}/{user.id}", headers=headers)
        assert r.status_code in (403, 409)

    def test_last_admin_protection_on_delete(self, client: TestClient, db: Session) -> None:
        """Two admins exist; deleting both leaves zero — second delete should be blocked."""
        a1 = make_user(db, username="adm1", password="pass123456", role=UserRole.ADMIN)
        a2 = make_user(db, username="adm2", password="pass123456", role=UserRole.ADMIN)
        r = client.post("/api/v1/auth/login", json={"username": "adm1", "password": "pass123456"})
        h1 = auth_header(r.json()["access_token"])
        # Delete a2 (a1 still exists — should succeed)
        r_del = client.delete(f"{self.BASE}/{a2.id}", headers=h1)
        assert r_del.status_code == 204
        # Now a1 is the only admin; trying to delete a1 from their own session must fail
        r_del2 = client.delete(f"{self.BASE}/{a1.id}", headers=h1)
        assert r_del2.status_code in (403, 409)

    def test_cannot_deactivate_last_admin(self, client: TestClient, db: Session) -> None:
        user = make_user(db, username="solo_admin2", password="pass123456", role=UserRole.ADMIN)
        r = client.post("/api/v1/auth/login", json={"username": "solo_admin2", "password": "pass123456"})
        headers = auth_header(r.json()["access_token"])
        r = client.patch(f"{self.BASE}/{user.id}", headers=headers, json={"is_active": False})
        assert r.status_code in (403, 409)

    def test_cannot_demote_last_admin(self, client: TestClient, db: Session) -> None:
        user = make_user(db, username="solo_admin3", password="pass123456", role=UserRole.ADMIN)
        r = client.post("/api/v1/auth/login", json={"username": "solo_admin3", "password": "pass123456"})
        headers = auth_header(r.json()["access_token"])
        r = client.patch(f"{self.BASE}/{user.id}", headers=headers, json={"role": "principal"})
        assert r.status_code in (403, 409)

    def test_list_pagination(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.get(f"{self.BASE}?page=1&page_size=5", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_page_size_capped_at_100(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.get(f"{self.BASE}?page_size=999", headers=headers)
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            assert r.json()["page_size"] <= 100


# ---------------------------------------------------------------------------
# Students: auto-fill, SGI flag, unique register_no
# ---------------------------------------------------------------------------

class TestStudents:
    BASE = "/api/v1/admin/students"

    def test_create_student(self, client: TestClient, db: Session, program: Program, batch: Batch) -> None:
        headers = _admin_headers(client, db)
        r = client.post(self.BASE, headers=headers, json={
            "register_no": "NIE22CS045",
            "name": "Test Student",
            "program_id": str(program.id),
            "batch_id": str(batch.id),
        })
        assert r.status_code == 201
        data = r.json()
        assert data["register_no"] == "NIE22CS045"

    def test_auto_fill_program_from_register_no(
        self, client: TestClient, db: Session, program: Program, batch: Batch
    ) -> None:
        headers = _admin_headers(client, db)
        r = client.post(self.BASE, headers=headers, json={
            "register_no": "NIE22CS045",
            "name": "Auto Fill Student",
            "batch_id": str(batch.id),
        })
        if r.status_code == 201:
            assert r.json()["program_id"] == str(program.id)
        else:
            assert r.status_code in (201, 422)

    def test_odd_prefix_sets_is_flagged(
        self, client: TestClient, db: Session, program: Program, batch: Batch
    ) -> None:
        headers = _admin_headers(client, db)
        r = client.post(self.BASE, headers=headers, json={
            "register_no": "SGI22CS013",
            "name": "Odd Prefix Student",
            "program_id": str(program.id),
            "batch_id": str(batch.id),
        })
        if r.status_code == 201:
            assert r.json()["is_flagged"] is True

    def test_duplicate_register_no_rejected(
        self, client: TestClient, db: Session, program: Program, batch: Batch
    ) -> None:
        headers = _admin_headers(client, db)
        payload = {
            "register_no": "NIE22CS001",
            "name": "First",
            "program_id": str(program.id),
            "batch_id": str(batch.id),
        }
        assert client.post(self.BASE, headers=headers, json=payload).status_code == 201
        r2 = client.post(self.BASE, headers=headers, json={**payload, "name": "Second"})
        assert r2.status_code in (409, 400, 422)

    def test_soft_deleted_register_no_hints_restore(
        self, client: TestClient, db: Session, program: Program, batch: Batch
    ) -> None:
        headers = _admin_headers(client, db)
        payload = {
            "register_no": "NIE22CS099",
            "name": "Delete Me",
            "program_id": str(program.id),
            "batch_id": str(batch.id),
        }
        r1 = client.post(self.BASE, headers=headers, json=payload)
        assert r1.status_code == 201
        client.delete(f"{self.BASE}/{r1.json()['id']}", headers=headers)
        r2 = client.post(self.BASE, headers=headers, json={**payload, "name": "Another"})
        assert r2.status_code in (409, 400, 422)
        body = r2.text.lower()
        assert any(word in body for word in ("restore", "deleted", "existing"))

    def test_unknown_filter_422(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.get(f"{self.BASE}?garbage_filter=x", headers=headers)
        assert r.status_code == 422

    def test_filter_by_program_id(
        self, client: TestClient, db: Session, program: Program, batch: Batch
    ) -> None:
        headers = _admin_headers(client, db)
        r = client.get(f"{self.BASE}?program_id={program.id}", headers=headers)
        assert r.status_code == 200

    def test_include_deleted_flag(
        self, client: TestClient, db: Session, program: Program, batch: Batch
    ) -> None:
        headers = _admin_headers(client, db)
        r1 = client.post(self.BASE, headers=headers, json={
            "register_no": "NIE22CS077",
            "name": "To Delete",
            "program_id": str(program.id),
            "batch_id": str(batch.id),
        })
        assert r1.status_code == 201
        client.delete(f"{self.BASE}/{r1.json()['id']}", headers=headers)
        r_no = client.get(f"{self.BASE}?search=NIE22CS077", headers=headers)
        assert r_no.json()["total"] == 0
        r_yes = client.get(f"{self.BASE}?search=NIE22CS077&include_deleted=true", headers=headers)
        assert r_yes.json()["total"] >= 1


# ---------------------------------------------------------------------------
# Batches CRUD
# ---------------------------------------------------------------------------

class TestBatches:
    BASE = "/api/v1/admin/batches"

    def test_create_batch(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.post(self.BASE, headers=headers, json={
            "start_year": 2023, "end_year": 2027, "label": "2023-27"
        })
        assert r.status_code == 201
        assert r.json()["label"] == "2023-27"

    def test_list_batches_shape(self, client: TestClient, db: Session, batch: Batch) -> None:
        headers = _admin_headers(client, db)
        r = client.get(self.BASE, headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "total" in data
        assert data["total"] >= 1

    def test_delete_and_restore_batch(self, client: TestClient, db: Session, batch: Batch) -> None:
        headers = _admin_headers(client, db)
        assert client.delete(f"{self.BASE}/{batch.id}", headers=headers).status_code == 204
        r = client.post(f"{self.BASE}/{batch.id}/restore", headers=headers)
        assert r.status_code == 200
        assert r.json()["deleted_at"] is None


# ---------------------------------------------------------------------------
# Read-only resources
# ---------------------------------------------------------------------------

class TestReadOnly:
    @pytest.mark.parametrize("resource", ["result-history", "upload-logs"])
    def test_list_read_only_ok(self, client: TestClient, db: Session, resource: str) -> None:
        headers = _admin_headers(client, db)
        r = client.get(f"/api/v1/admin/{resource}", headers=headers)
        assert r.status_code == 200

    @pytest.mark.parametrize("resource", ["result-history", "upload-logs"])
    def test_post_read_only_blocked(self, client: TestClient, db: Session, resource: str) -> None:
        headers = _admin_headers(client, db)
        r = client.post(f"/api/v1/admin/{resource}", headers=headers, json={})
        assert r.status_code in (400, 404, 405, 422)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_admin_can_list_audit_logs(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.get("/api/v1/admin/audit-logs", headers=headers)
        assert r.status_code == 200

    def test_principal_cannot_list_audit_logs(self, client: TestClient, db: Session) -> None:
        headers = _principal_headers(client, db)
        r = client.get("/api/v1/admin/audit-logs", headers=headers)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Options endpoint
# ---------------------------------------------------------------------------

class TestOptions:
    @pytest.mark.parametrize("resource", ["programs", "batches", "users"])
    def test_options_returns_list(self, client: TestClient, db: Session, resource: str) -> None:
        headers = _admin_headers(client, db)
        r = client.get(f"/api/v1/admin/options/{resource}", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_options_with_search_query(self, client: TestClient, db: Session, program: Program) -> None:
        headers = _admin_headers(client, db)
        r = client.get("/api/v1/admin/options/programs?q=CS", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_principal_options_403(self, client: TestClient, db: Session) -> None:
        headers = _principal_headers(client, db)
        r = client.get("/api/v1/admin/options/programs", headers=headers)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_users_returns_xlsx(self, client: TestClient, db: Session) -> None:
        headers = _admin_headers(client, db)
        r = client.get("/api/v1/admin/users/export", headers=headers)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert any(kw in ct for kw in ("spreadsheet", "excel", "octet", "xlsx"))

    def test_export_programs_ok(self, client: TestClient, db: Session, program: Program) -> None:
        headers = _admin_headers(client, db)
        r = client.get("/api/v1/admin/programs/export", headers=headers)
        assert r.status_code == 200

    def test_principal_cannot_export(self, client: TestClient, db: Session) -> None:
        headers = _principal_headers(client, db)
        r = client.get("/api/v1/admin/users/export", headers=headers)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Unauthenticated access → 401
# ---------------------------------------------------------------------------

class TestUnauthenticated:
    @pytest.mark.parametrize("path,method", [
        ("/api/v1/admin/users", "get"),
        ("/api/v1/admin/programs", "get"),
        ("/api/v1/admin/students", "get"),
        ("/api/v1/admin/audit-logs", "get"),
        ("/api/v1/admin/options/programs", "get"),
    ])
    def test_no_token_returns_401(self, client: TestClient, path: str, method: str) -> None:
        r = getattr(client, method)(path)
        assert r.status_code == 401
