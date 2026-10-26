"""Bulk data import from data/ folder.

Steps:
  1. Import students from  data/CS,ME,MC,CE.xlsx
  2. Extract every PDF from each ZIP in data/:
       - Grade Card PDFs  -> GradeCard + SemesterResult rows
       - Course Book PDFs -> Subject + Faculty + CourseOffering rows
       - Other PDFs       -> skipped with a warning

Usage:
    .venv\Scripts\python scripts/bulk_import.py
"""

from __future__ import annotations

import io
import logging
import re
import sys
import zipfile
from pathlib import Path

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.modules.faculty.models import CourseOffering, Faculty, Subject, SubjectType
from app.modules.results.models import (
    ExamSession,
    ExamType,
    Grade,
    GradeCard,
    ResultStatus,
    SemesterResult,
)
from app.modules.students.models import Batch, Program, Student, StudentStatus
from app.modules.uploads.parsers.course_book_pdf import CourseBookPdfParser
from app.modules.uploads.parsers.detector import detect_file_type
from app.modules.uploads.parsers.grade_card_pdf import GradeCardPdfParser

configure_logging()
logger = logging.getLogger("scripts.bulk_import")

DATA_DIR = Path(__file__).parent.parent / "data"

SHEET_PROGRAM_MAP: dict[str, str] = {
    "ME": "ME",
    "MC": "MC",
    "CE": "CE",
    "CSE": "CS",
}

PROGRAM_NAMES: dict[str, str] = {
    "CS": "Computer Science and Engineering",
    "ME": "Mechanical Engineering",
    "MC": "Mechatronics Engineering",
    "CE": "Civil Engineering",
    "AD": "Artificial Intelligence and Data Science",
    "CC": "Computer Science and Engineering (Cyber Security)",
}

REG_PREFIX_MAP: dict[str, str] = {
    "CS": "CS",
    "CSE": "CS",
    "LCSE": "CS",
    "ME": "ME",
    "LME": "ME",
    "MC": "MC",
    "MCTR": "MC",
    "LMCTR": "MC",
    "LMC": "MC",
    "CE": "CE",
    "LCE": "CE",
    "AD": "AD",
    "CC": "CC",
}

_REG_RE = re.compile(r"(?:NIE)?(\d{2})([A-Z]+)(\d+)", re.IGNORECASE)


def _guess_program_from_reg(reg: str) -> str | None:
    m = _REG_RE.search(reg.upper().replace(" ", ""))
    if not m:
        return None
    return REG_PREFIX_MAP.get(m.group(2).upper())


def _admission_year_from_reg(reg: str) -> int:
    m = _REG_RE.search(reg.upper().replace(" ", ""))
    if m:
        return 2000 + int(m.group(1))
    return 2022


# ---------------------------------------------------------------------------
# Shared DB helpers
# ---------------------------------------------------------------------------

def _get_or_create_program(db: Session, code: str) -> Program:
    code = code.upper()
    p = db.execute(select(Program).where(Program.code == code)).scalar_one_or_none()
    if not p:
        p = Program(code=code, name=PROGRAM_NAMES.get(code, code), is_active=True)
        db.add(p)
        db.flush()
    return p


def _get_or_create_batch(db: Session, start_year: int) -> Batch:
    b = db.execute(select(Batch).where(Batch.start_year == start_year)).scalar_one_or_none()
    if not b:
        end_year = start_year + 4
        b = Batch(start_year=start_year, end_year=end_year, label=f"{start_year}-{str(end_year)[-2:]}")
        db.add(b)
        db.flush()
    return b


def _get_or_create_exam_session(db: Session, name: str) -> ExamSession:
    es = db.execute(select(ExamSession).where(ExamSession.name == name)).scalar_one_or_none()
    if not es:
        es = ExamSession(name=name, exam_type=ExamType.REGULAR, scheme="2019")
        db.add(es)
        db.flush()
    return es


def _get_or_create_subject(db: Session, code: str, name: str, sem: int) -> Subject:
    s = db.execute(
        select(Subject).where(Subject.code == code, Subject.scheme == "2019")
    ).scalar_one_or_none()
    if not s:
        s = Subject(code=code, name=name or code, semester=sem, scheme="2019", type=SubjectType.THEORY)
        db.add(s)
        db.flush()
    return s


def _upsert_student(db: Session, reg: str, name: str, prog_code: str, adm_year: int) -> Student:
    prog = _get_or_create_program(db, prog_code)
    batch = _get_or_create_batch(db, adm_year)
    st = db.execute(select(Student).where(Student.register_no == reg)).scalar_one_or_none()
    if st:
        st.name = name or st.name
        st.program_id = prog.id
        st.batch_id = batch.id
        st.deleted_at = None
    else:
        logger.warning("  Auto-creating student not in Excel: reg=%s name=%s prog=%s", reg, name, prog_code)
        st = Student(
            register_no=reg,
            name=name,
            program_id=prog.id,
            batch_id=batch.id,
            status=StudentStatus.ACTIVE,
        )
        db.add(st)
    db.flush()
    return st


# ---------------------------------------------------------------------------
# Step 1: Students from Excel
# ---------------------------------------------------------------------------

def import_students_from_excel(db: Session) -> int:
    excel_path = DATA_DIR / "CS,ME,MC,CE.xlsx"
    if not excel_path.exists():
        logger.warning("Excel file not found: %s", excel_path)
        return 0
    wb = openpyxl.load_workbook(excel_path)
    total = 0
    for sheet_name, prog_code in SHEET_PROGRAM_MAP.items():
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        count = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            reg_raw, name_raw = row[0], row[1]
            if not reg_raw:
                continue
            reg = str(reg_raw).strip().replace(" ", "")
            name = str(name_raw).strip() if name_raw else reg
            if not _REG_RE.search(reg.upper()):
                logger.warning("Skipping odd register no '%s' (%s)", reg, sheet_name)
                continue
            adm_year = _admission_year_from_reg(reg)
            _upsert_student(db, reg, name, prog_code, adm_year)
            count += 1
        db.commit()
        logger.info("Imported %d students from sheet '%s'", count, sheet_name)
        total += count
    return total


# ---------------------------------------------------------------------------
# Step 2a: Grade Card PDF ingestion
# ---------------------------------------------------------------------------

_REVAL_RE = re.compile(r"revaluation|reval", re.IGNORECASE)


def _extract_session_name(text: str, sem: int) -> str:
    m = re.search(
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
        r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        return f"{m.group(1)[:3].capitalize()} {m.group(2)}"
    return f"S{sem} Exam"


def _ingest_grade_card_pdf(db: Session, pdf_bytes: bytes, zip_name: str, pdf_name: str) -> dict:
    parser = GradeCardPdfParser()
    result = parser.parse(pdf_bytes)

    if not result.rows:
        for err in result.errors:
            logger.debug("  [parse-error] %s pg=%s row=%s: %s", err.code, err.page, err.row, err.message)
        return {"skipped": True, "errors": len(result.errors)}

    if result.errors:
        for err in result.errors:
            logger.warning(
                "  [parse-error] %s | %s | pg=%s row=%s | %s",
                pdf_name[:40],
                err.code,
                err.page,
                err.row,
                err.message,
            )

    meta = result.meta or {}
    sem = meta.get("semester") or 1

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            first_text = pdf.pages[0].extract_text() or "" if pdf.pages else ""
    except Exception:
        first_text = ""

    is_reval = bool(_REVAL_RE.search(first_text[:500]))
    session_name = _extract_session_name(first_text, sem)
    es = _get_or_create_exam_session(db, session_name)

    new_students = 0
    skipped_students = 0
    grade_cards_written = 0

    for r in result.rows:
        reg = r.get("register_no", "").strip().replace(" ", "")
        if not reg:
            continue

        st = db.execute(select(Student).where(Student.register_no == reg)).scalar_one_or_none()
        if not st:
            prog_code = r.get("program_code") or _guess_program_from_reg(reg)
            if not prog_code:
                logger.warning("  Cannot determine program for reg='%s' -- skipping student", reg)
                skipped_students += 1
                continue
            adm_year = _admission_year_from_reg(reg)
            name = r.get("name", reg)
            st = _upsert_student(db, reg, name, prog_code, adm_year)
            new_students += 1

        gc = db.execute(
            select(GradeCard).where(
                GradeCard.student_id == st.id,
                GradeCard.semester == sem,
                GradeCard.exam_session_id == es.id,
            )
        ).scalar_one_or_none()

        if gc:
            if r.get("sgpa") is not None:
                gc.sgpa = r["sgpa"]
            if r.get("cgpa") is not None:
                gc.cgpa = r["cgpa"]
            if r.get("earned_credits") is not None:
                gc.earned_credits = r["earned_credits"]
            if r.get("cumulative_credits") is not None:
                gc.cumulative_credits = r["cumulative_credits"]
            gc.deleted_at = None
        else:
            gc = GradeCard(
                student_id=st.id,
                semester=sem,
                exam_session_id=es.id,
                earned_credits=r.get("earned_credits"),
                cumulative_credits=r.get("cumulative_credits"),
                sgpa=r.get("sgpa"),
                cgpa=r.get("cgpa"),
            )
            db.add(gc)

        db.flush()
        grade_cards_written += 1

        for cr in r.get("course_results", []):
            c_code = cr["course_code"]
            g_str = cr["grade"]
            st_str = cr.get("status", "pass")
            cr_sem = cr.get("semester", sem)

            subject = _get_or_create_subject(db, c_code, c_code, cr_sem)

            sr = db.execute(
                select(SemesterResult).where(
                    SemesterResult.student_id == st.id,
                    SemesterResult.subject_id == subject.id,
                    SemesterResult.exam_session_id == es.id,
                )
            ).scalar_one_or_none()

            try:
                grade_enum = Grade(g_str)
            except ValueError:
                grade_enum = None

            try:
                status_enum = ResultStatus(st_str)
            except ValueError:
                status_enum = ResultStatus.PASS

            if sr:
                sr.grade = grade_enum
                sr.status = status_enum
                sr.semester = cr_sem
                sr.deleted_at = None
            else:
                sr = SemesterResult(
                    student_id=st.id,
                    subject_id=subject.id,
                    exam_session_id=es.id,
                    semester=cr_sem,
                    grade=grade_enum,
                    status=status_enum,
                    is_regular_attempt=not is_reval,
                )
                db.add(sr)

    db.commit()
    return {
        "type": "grade_card",
        "rows": len(result.rows),
        "grade_cards": grade_cards_written,
        "new_students": new_students,
        "skipped_students": skipped_students,
        "parse_errors": len(result.errors),
    }


# ---------------------------------------------------------------------------
# Step 2b: Course Book PDF ingestion  (NEW)
# ---------------------------------------------------------------------------

def _ingest_course_book_pdf(db: Session, pdf_bytes: bytes, zip_name: str, pdf_name: str) -> dict:
    parser = CourseBookPdfParser()
    result = parser.parse(pdf_bytes)

    if not result.rows:
        for err in result.errors:
            logger.debug("  [parse-error] %s pg=%s: %s", err.code, err.page, err.message)
        return {"skipped": True, "type": "course_book", "errors": len(result.errors)}

    if result.errors:
        for err in result.errors:
            logger.warning(
                "  [parse-error] %s | %s | pg=%s | %s",
                pdf_name[:40],
                err.code,
                err.page,
                err.message,
            )

    meta = result.meta or {}
    default_sem = meta.get("semester") or 1
    default_ay = meta.get("academic_year") or "2022-23"
    default_prog = meta.get("program_code") or "CS"

    m_yr = re.search(r"\d{4}", default_ay)
    adm_yr = int(m_yr.group()) if m_yr else 2022

    offerings_written = 0
    subjects_created = 0
    faculty_upserted = 0

    for r in result.rows:
        course_code = r.get("course_code", "UNKNOWN")
        course_name = r.get("course_name") or course_code
        sem = r.get("semester", default_sem)
        ay = r.get("academic_year", default_ay)
        prog_code = r.get("program_code", default_prog)
        slot = r.get("slot", "A")

        prog = _get_or_create_program(db, prog_code)
        batch = _get_or_create_batch(db, adm_yr)

        existing_subject = db.execute(
            select(Subject).where(Subject.code == course_code, Subject.scheme == "2019")
        ).scalar_one_or_none()
        if not existing_subject:
            subjects_created += 1
        subject = _get_or_create_subject(db, course_code, course_name, sem)

        for fac in r.get("faculty", []):
            ktu_id = fac.get("ktu_id")
            fac_name = fac.get("name") or "Unknown Faculty"
            phone = fac.get("phone")
            email = fac.get("email")
            part = fac.get("part_label")
            is_main = fac.get("is_main_faculty", True)

            faculty_obj = None
            if ktu_id:
                faculty_obj = db.execute(
                    select(Faculty).where(Faculty.ktu_id == ktu_id)
                ).scalar_one_or_none()
            if not faculty_obj:
                faculty_obj = Faculty(
                    name=fac_name,
                    ktu_id=ktu_id,
                    phone=phone,
                    email=email,
                    department_id=prog.id,
                    is_active=True,
                )
                db.add(faculty_obj)
                db.flush()
            else:
                if phone:
                    faculty_obj.phone = phone
                if email:
                    faculty_obj.email = email
            faculty_upserted += 1

            offering = db.execute(
                select(CourseOffering).where(
                    CourseOffering.subject_id == subject.id,
                    CourseOffering.faculty_id == faculty_obj.id,
                    CourseOffering.batch_id == batch.id,
                    CourseOffering.academic_year == ay,
                    CourseOffering.semester == sem,
                    CourseOffering.slot == slot,
                    CourseOffering.part_label == part,
                )
            ).scalar_one_or_none()

            if not offering:
                offering = CourseOffering(
                    subject_id=subject.id,
                    faculty_id=faculty_obj.id,
                    batch_id=batch.id,
                    program_id=prog.id,
                    semester=sem,
                    academic_year=ay,
                    slot=slot,
                    part_label=part,
                    is_main_faculty=is_main,
                )
                db.add(offering)
                offerings_written += 1

    db.commit()
    return {
        "type": "course_book",
        "rows": len(result.rows),
        "offerings": offerings_written,
        "faculty": faculty_upserted,
        "subjects_created": subjects_created,
        "parse_errors": len(result.errors),
    }


# ---------------------------------------------------------------------------
# Step 2: Dispatch all PDFs in all ZIPs
# ---------------------------------------------------------------------------

def import_pdfs_from_zips(db: Session) -> dict:
    zip_files = sorted(DATA_DIR.glob("*.zip"))
    totals: dict = {
        "zips": 0,
        "pdfs": 0,
        "grade_cards": 0,
        "new_students": 0,
        "skipped_students": 0,
        "offerings": 0,
        "faculty": 0,
        "subjects_created": 0,
        "skipped_pdfs": 0,
        "parse_errors": 0,
    }

    for zip_path in zip_files:
        logger.info("Processing ZIP: %s", zip_path.name)
        totals["zips"] += 1
        try:
            with zipfile.ZipFile(zip_path) as zf:
                pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
                for pdf_name in pdf_names:
                    try:
                        pdf_bytes = zf.read(pdf_name)
                    except Exception as exc:
                        logger.warning("  Could not read '%s': %s", pdf_name, exc)
                        totals["skipped_pdfs"] += 1
                        continue

                    detected = detect_file_type(pdf_bytes)

                    if detected in ("grade_card", "result", "revaluation"):
                        stats = _ingest_grade_card_pdf(db, pdf_bytes, zip_path.name, pdf_name)
                    elif detected == "course_book":
                        stats = _ingest_course_book_pdf(db, pdf_bytes, zip_path.name, pdf_name)
                    else:
                        logger.warning("  Unrecognised file type for '%s' -- skipping", pdf_name)
                        totals["skipped_pdfs"] += 1
                        continue

                    totals["pdfs"] += 1

                    if stats.get("skipped"):
                        totals["skipped_pdfs"] += 1
                    else:
                        totals["parse_errors"] += stats.get("parse_errors", 0)

                        if stats.get("type") == "course_book":
                            totals["offerings"] += stats.get("offerings", 0)
                            totals["faculty"] += stats.get("faculty", 0)
                            totals["subjects_created"] += stats.get("subjects_created", 0)
                            logger.info(
                                "  [course_book] %-36s rows=%s offerings=%s faculty=%s errs=%s",
                                pdf_name[:36],
                                stats.get("rows", "?"),
                                stats.get("offerings", "?"),
                                stats.get("faculty", "?"),
                                stats.get("parse_errors", "?"),
                            )
                        else:
                            totals["grade_cards"] += stats.get("grade_cards", 0)
                            totals["new_students"] += stats.get("new_students", 0)
                            totals["skipped_students"] += stats.get("skipped_students", 0)
                            logger.info(
                                "  [grade_card]  %-36s rows=%s gc=%s new_stu=%s errs=%s",
                                pdf_name[:36],
                                stats.get("rows", "?"),
                                stats.get("grade_cards", "?"),
                                stats.get("new_students", "?"),
                                stats.get("parse_errors", "?"),
                            )
        except zipfile.BadZipFile as exc:
            logger.error("Bad ZIP '%s': %s", zip_path.name, exc)

    return totals


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    db = SessionLocal()
    try:
        print("\n=== Step 1: Importing students from Excel ===")
        n_students = import_students_from_excel(db)
        print(f"  -> {n_students} students imported/updated\n")

        print("=== Step 2: Importing PDFs from ZIPs ===")
        stats = import_pdfs_from_zips(db)
        print(
            f"\n=== Done ===\n"
            f"  ZIPs processed     : {stats.get('zips', 0)}\n"
            f"  PDFs attempted     : {stats.get('pdfs', 0)}\n"
            f"  PDFs skipped       : {stats.get('skipped_pdfs', 0)}\n"
            f"\n  --- Grade Card Results ---\n"
            f"  Grade cards written: {stats.get('grade_cards', 0)}\n"
            f"  New students added : {stats.get('new_students', 0)}\n"
            f"  Students skipped   : {stats.get('skipped_students', 0)}\n"
            f"\n  --- Course Book Results ---\n"
            f"  Subjects created   : {stats.get('subjects_created', 0)}\n"
            f"  Faculty upserted   : {stats.get('faculty', 0)}\n"
            f"  Offerings written  : {stats.get('offerings', 0)}\n"
            f"\n  Parse errors total : {stats.get('parse_errors', 0)}\n"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
