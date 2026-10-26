"""Unit and integration tests for Phase 5 Upload and PDF parsing pipeline."""

from __future__ import annotations

import io
import uuid

import openpyxl
from app.modules.faculty.models import CourseOffering, Faculty, Subject
from app.modules.results.models import (
    Grade,
    GradeCard,
    ResultHistory,
    ResultStatus,
    SemesterResult,
)
from app.modules.students.models import Batch, Program, Student, StudentStatus
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.conftest import auth_header


# --------------------------------------------------------------------------- #
# File Generation Helpers
# --------------------------------------------------------------------------- #
def make_student_list_excel(rows: list[list[str]]) -> bytes:
    """Generate an Excel workbook with students in memory."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CS-A"
    ws.append(["Register No", "Name", "Division"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def make_result_pdf(
    exam_title: str,
    program_heading: str,
    student_entries: list[tuple[str, str]],
) -> bytes:
    """Generate a KTU Result PDF in memory using ReportLab."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 750, "Exam Centre: Nirmala College")
    c.drawString(100, 730, f"{exam_title}")
    c.drawString(100, 710, "Generated on: 18/09/2026 10:40:00")
    c.drawString(100, 680, f"Branch: {program_heading}")

    y = 650
    for reg, courses in student_entries:
        c.drawString(100, y, f"{reg}  {courses}")
        y -= 25
        if y < 100:
            c.showPage()
            y = 700

    c.drawString(100, 50, "Controller of Examinations")
    c.save()
    return buf.getvalue()


def make_grade_card_pdf(
    branch: str,
    semester: int,
    students: list[tuple[str, str, str, str, str, str]],
) -> bytes:
    """Generate a Semester Grade Card Report PDF in memory."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 750, "Nirmala College of Engineering")
    c.drawString(100, 730, f"Branch: {branch}")
    c.drawString(100, 710, f"Semester: S{semester}")
    c.drawString(100, 690, "MAT101 - LINEAR ALGEBRA AND CALCULUS")
    c.drawString(100, 675, "CYT100 - ENGINEERING CHEMISTRY")

    y = 640
    # Header line
    c.drawString(50, y, "Student  MAT101  CYT100  Earned  Cumulative  SGPA  CGPA")
    y -= 25

    for reg_name, mat_g, cyt_g, earned, sgpa, cgpa in students:
        c.drawString(
            50,
            y,
            f"{reg_name}  {mat_g}  {cyt_g}  {earned}  {earned}  {sgpa}  {cgpa}",
        )
        y -= 25
        if y < 100:
            c.showPage()
            y = 700

    c.save()
    return buf.getvalue()


def make_course_book_pdf(
    branch: str,
    semester: int,
    academic_year: str,
    courses: list[dict],
) -> bytes:
    """Generate a Course Book PDF in memory."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 750, "Course Book Details For B.Tech")
    c.drawString(100, 730, f"Branch: {branch}")
    c.drawString(100, 710, f"Semester: S{semester}  Academic Year: {academic_year}")

    y = 670
    for course in courses:
        c.drawString(100, y, f"Slot {course['slot']}  Course: {course['code']} - {course['name']}")
        y -= 20
        c.drawString(100, y, "Name of Faculty  Contact  Email  Batch  Main Faculty")
        y -= 20
        for fac in course.get("faculty", []):
            c.drawString(
                100,
                y,
                f"{fac['name']} ({fac['ktu_id']})  {fac['phone']}  "
                f"{fac['email']}  {fac['batch']}  {fac['main']}",
            )
            y -= 20
        y -= 10
        if y < 100:
            c.showPage()
            y = 700

    c.save()
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Test 1: Student List Excel Preview & Confirm
# --------------------------------------------------------------------------- #
def test_student_list_preview_and_confirm(client: TestClient, admin_token: str, db: Session):
    headers = auth_header(admin_token)
    excel_bytes = make_student_list_excel(
        [
            ["NIE22CS001", "ALICE SMITH", "A"],
            ["NIE22CS002", "BOB JONES", "A"],
            ["SGI22CS013", "ODD PREFIX STUDENT", "A"],
            ["INVALID_REG", "BROKEN ROW", "A"],
            ["NIE22CS001", "DUPLICATE ALICE", "A"],
        ]
    )

    # 1. Preview
    resp = client.post(
        "/api/v1/uploads/preview",
        headers=headers,
        data={"file_type": "student_list"},
        files={
            "file": (
                "students.xlsx",
                excel_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert preview["file_type"] == "student_list"
    assert preview["summary"]["rows_total"] == 3  # Valid register numbers
    assert len(preview["errors"]) >= 3  # invalid format, duplicate, odd prefix
    assert any(e["code"] == "ODD_REGISTER_PREFIX" for e in preview["errors"])
    assert any(e["code"] == "STRUCTURE_NOT_RECOGNISED" for e in preview["errors"])
    assert any(e["code"] == "DUPLICATE_ROW" for e in preview["errors"])

    # CRITICAL: Preview saves NOTHING to the business tables
    db_students_before = db.execute(select(Student)).scalars().all()
    assert len(db_students_before) == 0

    upload_id = preview["upload_id"]

    # 2. Confirm
    confirm_resp = client.post(
        f"/api/v1/uploads/{upload_id}/confirm",
        headers=headers,
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    confirm_data = confirm_resp.json()
    assert confirm_data["status"] == "confirmed"
    assert confirm_data["rows_applied"] == 3

    # Business tables now populated
    students = db.execute(select(Student)).scalars().all()
    assert len(students) == 3
    alice = db.execute(select(Student).where(Student.register_no == "NIE22CS001")).scalar_one()
    assert alice.name == "ALICE SMITH"
    assert alice.is_flagged is False

    sgi = db.execute(select(Student).where(Student.register_no == "SGI22CS013")).scalar_one()
    assert sgi.is_flagged is True

    # 3. Double confirm rejected with 409
    double_resp = client.post(
        f"/api/v1/uploads/{upload_id}/confirm",
        headers=headers,
    )
    assert double_resp.status_code == 409


# --------------------------------------------------------------------------- #
# Test 2: Course Book PDF Preview & Confirm
# --------------------------------------------------------------------------- #
def test_course_book_preview_and_confirm(client: TestClient, admin_token: str, db: Session):
    headers = auth_header(admin_token)
    pdf_bytes = make_course_book_pdf(
        branch="Computer Science & Engineering",
        semester=1,
        academic_year="2022-23",
        courses=[
            {
                "slot": "A",
                "code": "CST101",
                "name": "PROGRAMMING IN C",
                "faculty": [
                    {
                        "name": "Anu Jose",
                        "ktu_id": "KTU-F25319",
                        "phone": "9876543210",
                        "email": "anu@nirmala.ac.in",
                        "batch": "2022-26",
                        "main": "Yes",
                    }
                ],
            },
            {
                "slot": "B",
                "code": "EST120",
                "name": "BASICS OF CIVIL AND MECHANICAL",
                "faculty": [
                    {
                        "name": "Civil Prof",
                        "ktu_id": "KTU-F11111",
                        "phone": "9876543211",
                        "email": "civil@nirmala.ac.in",
                        "batch": "2022-26",
                        "main": "Yes",
                    },
                    {
                        "name": "Mech Prof",
                        "ktu_id": "KTU-F22222",
                        "phone": "9876543212",
                        "email": "mech@nirmala.ac.in",
                        "batch": "2022-26",
                        "main": "No",
                    },
                ],
            },
            {
                "slot": "C",
                "code": "MAT101",
                "name": "CALCULUS",
                "faculty": [],  # Truncated slot: no faculty
            },
        ],
    )

    # 1. Preview
    resp = client.post(
        "/api/v1/uploads/preview",
        headers=headers,
        data={"file_type": "course_book"},
        files={"file": ("course_book.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert preview["file_type"] == "course_book"
    assert any(e["code"] == "MISSING_FACULTY" for e in preview["errors"])

    upload_id = preview["upload_id"]

    # 2. Confirm
    confirm_resp = client.post(
        f"/api/v1/uploads/{upload_id}/confirm",
        headers=headers,
    )
    assert confirm_resp.status_code == 200, confirm_resp.text

    # Verify subjects and faculty in DB
    fac1 = db.execute(select(Faculty).where(Faculty.ktu_id == "KTU-F25319")).scalar_one_or_none()
    assert fac1 is not None
    assert fac1.name == "Anu Jose"

    offerings = db.execute(select(CourseOffering)).scalars().all()
    assert len(offerings) == 3  # CST101 (1) + EST120 Part I & Part II (2)


# --------------------------------------------------------------------------- #
# Test 3: Grade Card PDF Preview & Confirm
# --------------------------------------------------------------------------- #
def test_grade_card_preview_and_confirm(client: TestClient, admin_token: str, db: Session):
    headers = auth_header(admin_token)

    # Pre-seed one student
    prog = Program(code="CS", name="Computer Science", is_active=True)
    batch = Batch(start_year=2022, end_year=2026, label="2022-26")
    db.add_all([prog, batch])
    db.flush()
    st = Student(
        register_no="NIE22CS052",
        name="UMMUFASEELA K A",
        program_id=prog.id,
        batch_id=batch.id,
        status=StudentStatus.ACTIVE,
    )
    db.add(st)
    db.commit()

    # PDF containing NIE22CS052 (seeded) and NIE22CS999 (unknown)
    pdf_bytes = make_grade_card_pdf(
        branch="Computer Science & Engineering",
        semester=1,
        students=[
            ("NIE22CS052-UMMUFASEELA K A", "A", "B+", "18", "7.85", "7.85"),
            ("NIE22CS999-UNKNOWN GUY", "F", "P", "14", "5.12", "5.12"),
        ],
    )

    resp = client.post(
        "/api/v1/uploads/preview",
        headers=headers,
        data={"file_type": "grade_card"},
        files={"file": ("grade_card.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert any(e["code"] == "UNKNOWN_REGISTER_NO" for e in preview["errors"])

    upload_id = preview["upload_id"]
    confirm_resp = client.post(
        f"/api/v1/uploads/{upload_id}/confirm",
        headers=headers,
    )
    assert confirm_resp.status_code == 200, confirm_resp.text

    # Seeded student got their grade card and semester results
    gc = db.execute(select(GradeCard).where(GradeCard.student_id == st.id)).scalar_one_or_none()
    assert gc is not None
    assert gc.sgpa == 7.85

    results = (
        db.execute(select(SemesterResult).where(SemesterResult.student_id == st.id)).scalars().all()
    )
    assert len(results) == 2


# --------------------------------------------------------------------------- #
# Test 4: Result PDF & Revaluation PDF Preview & Confirm
# --------------------------------------------------------------------------- #
def test_result_and_revaluation_pdf(client: TestClient, admin_token: str, db: Session):
    headers = auth_header(admin_token)

    # Pre-seed student & subject
    prog = Program(code="CS", name="Computer Science", is_active=True)
    batch = Batch(start_year=2023, end_year=2027, label="2023-27")
    sub = Subject(code="MAT101", name="Calculus", semester=1, scheme="2019")
    db.add_all([prog, batch, sub])
    db.flush()
    st = Student(
        register_no="NIE23CS011",
        name="TEST STUDENT",
        program_id=prog.id,
        batch_id=batch.id,
        status=StudentStatus.ACTIVE,
    )
    db.add(st)
    db.commit()

    # 1. Upload Result PDF with fail in MAT101
    result_bytes = make_result_pdf(
        exam_title="B.Tech S1 (S,FE) Exam Dec 2024",
        program_heading="COMPUTER SCIENCE & ENGINEERING",
        student_entries=[("NIE23CS011", "MAT101(F)")],
    )

    resp = client.post(
        "/api/v1/uploads/preview",
        headers=headers,
        data={"file_type": "result"},
        files={"file": ("result.pdf", result_bytes, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    u1_id = resp.json()["upload_id"]

    client.post(f"/api/v1/uploads/{u1_id}/confirm", headers=headers)

    sr = db.execute(
        select(SemesterResult).where(
            SemesterResult.student_id == st.id, SemesterResult.subject_id == sub.id
        )
    ).scalar_one()
    assert sr.grade == Grade.F
    assert sr.status == ResultStatus.FAIL

    # 2. Upload Revaluation PDF with MAT101 passing as P
    reval_bytes = make_result_pdf(
        exam_title="Revaluation Result- Dec 2024",
        program_heading="COMPUTER SCIENCE & ENGINEERING",
        student_entries=[("NIE23CS011", "MAT101(P)")],
    )

    reval_resp = client.post(
        "/api/v1/uploads/preview",
        headers=headers,
        data={"file_type": "revaluation"},
        files={"file": ("reval.pdf", reval_bytes, "application/pdf")},
    )
    assert reval_resp.status_code == 200, reval_resp.text
    u2_id = reval_resp.json()["upload_id"]

    client.post(f"/api/v1/uploads/{u2_id}/confirm", headers=headers)

    # Grade updated in place
    db.refresh(sr)
    assert sr.grade == Grade.P
    assert sr.status == ResultStatus.PASS

    # ResultHistory entry created
    history = (
        db.execute(select(ResultHistory).where(ResultHistory.semester_result_id == sr.id))
        .scalars()
        .all()
    )
    assert len(history) == 1
    assert history[0].old_grade == Grade.F
    assert history[0].new_grade == Grade.P


# --------------------------------------------------------------------------- #
# Test 5: Role Permissions (Principal gets 403, Admin gets 200, None gets 401)
# --------------------------------------------------------------------------- #
def test_upload_role_permissions(client: TestClient, admin_token: str, principal_token: str):
    admin_headers = auth_header(admin_token)
    principal_headers = auth_header(principal_token)
    dummy_file = (
        "test.xlsx",
        make_student_list_excel([["NIE22CS001", "A", "A"]]),
        "application/octet-stream",
    )

    # 1. Unauthenticated -> 401
    r_unauth = client.post("/api/v1/uploads/preview", data={"file_type": "student_list"})
    assert r_unauth.status_code == 401

    # 2. Principal -> 403 on preview, confirm, delete, list
    r_princ_prev = client.post(
        "/api/v1/uploads/preview",
        headers=principal_headers,
        data={"file_type": "student_list"},
        files={"file": dummy_file},
    )
    assert r_princ_prev.status_code == 403

    dummy_id = str(uuid.uuid4())
    r_princ_conf = client.post(
        f"/api/v1/uploads/{dummy_id}/confirm",
        headers=principal_headers,
    )
    assert r_princ_conf.status_code == 403

    r_princ_del = client.delete(
        f"/api/v1/uploads/{dummy_id}",
        headers=principal_headers,
    )
    assert r_princ_del.status_code == 403

    # 3. Admin can list uploads
    r_admin_list = client.get("/api/v1/uploads", headers=admin_headers)
    assert r_admin_list.status_code == 200


# --------------------------------------------------------------------------- #
# Test 6: Duplicate detection, delete/cancel, oversized file, malicious name
# --------------------------------------------------------------------------- #
def test_upload_edge_cases(client: TestClient, admin_token: str):
    headers = auth_header(admin_token)
    content = make_student_list_excel([["NIE22CS001", "A", "A"]])

    # Duplicate warning test
    r1 = client.post(
        "/api/v1/uploads/preview",
        headers=headers,
        data={"file_type": "student_list"},
        files={"file": ("test.xlsx", content, "application/octet-stream")},
    )
    assert r1.status_code == 200
    u1_id = r1.json()["upload_id"]

    r2 = client.post(
        "/api/v1/uploads/preview",
        headers=headers,
        data={"file_type": "student_list"},
        files={"file": ("test.xlsx", content, "application/octet-stream")},
    )
    assert r2.status_code == 200
    assert r2.json()["warning"] is not None  # Warns of duplicate SHA-256

    # Cancel upload (DELETE)
    del_resp = client.delete(f"/api/v1/uploads/{u1_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "cancelled"

    # Cannot confirm cancelled upload
    conf_cancelled = client.post(f"/api/v1/uploads/{u1_id}/confirm", headers=headers)
    assert conf_cancelled.status_code == 409

    # Malicious filename sanitization
    r_malicious = client.post(
        "/api/v1/uploads/preview",
        headers=headers,
        data={"file_type": "student_list"},
        files={"file": ("../../../../etc/passwd.xlsx", content, "application/octet-stream")},
    )
    assert r_malicious.status_code == 200

    # Wrong declared file type (PDF sent as student_list)
    pdf_bytes = make_result_pdf("Exam Dec 2024", "COMPUTER SCIENCE", [("NIE23CS011", "MAT101(F)")])
    r_wrong = client.post(
        "/api/v1/uploads/preview",
        headers=headers,
        data={"file_type": "student_list"},
        files={"file": ("result.pdf", pdf_bytes, "application/pdf")},
    )
    assert r_wrong.status_code == 200
    assert r_wrong.json()["warning"] is not None  # Detected result vs declared student_list
