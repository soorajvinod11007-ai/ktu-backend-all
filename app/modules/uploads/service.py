"""Service layer for file uploads, preview generation, validation, and confirmation."""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationFailedError,
)
from app.modules.faculty.models import CourseOffering, Faculty, Subject, SubjectType
from app.modules.results.models import (
    ChangeType,
    ExamSession,
    ExamType,
    Grade,
    GradeCard,
    ResultHistory,
    ResultStatus,
    SemesterResult,
)
from app.modules.students.models import Batch, Division, Program, Student, StudentStatus
from app.modules.uploads.models import UploadFileType, UploadLog, UploadStatus
from app.modules.uploads.parsers import (
    ErrorCode,
    ParseError,
    detect_file_type,
    get_parser,
)
from app.modules.uploads.repository import UploadRepository


class UploadService:
    @staticmethod
    def preview_upload(
        db: Session,
        user: Any,
        file: UploadFile,
        file_type_str: str,
        exam_session_id: uuid.UUID | None = None,
        allow_duplicate: bool = False,
    ) -> dict[str, Any]:
        settings = get_settings()
        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

        # Read file data and check size limit
        data = file.file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValidationFailedError(
                f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_MB} MB.",
                details=[{"max_bytes": max_bytes, "received": len(data)}],
            )

        client_filename = file.filename or "upload.dat"
        # Sanitize filename against directory traversal / malicious names
        safe_base = Path(client_filename).name
        ext = safe_base.rsplit(".", 1)[-1].lower() if "." in safe_base else "bin"

        # Check declared file_type
        try:
            declared_type = UploadFileType(file_type_str.lower())
        except ValueError:
            allowed = [t.value for t in UploadFileType]
            raise ValidationFailedError(
                f"Invalid file_type '{file_type_str}'. Allowed: {allowed}",
                details=[{"field": "file_type", "value": file_type_str}],
            ) from None

        # Detect content type from content bytes
        detected_type = detect_file_type(data)
        warning_msg: str | None = None
        if detected_type and detected_type != declared_type.value:
            warning_msg = (
                f"Detected file content appears to be '{detected_type}', "
                f"which differs from declared file_type '{declared_type.value}'."
            )

        # SHA-256 duplicate detection
        file_hash = hashlib.sha256(data).hexdigest()
        existing_log = UploadRepository.get_by_hash(db, file_hash)
        if existing_log and not allow_duplicate:
            warning_msg = (
                f"Duplicate file: matches previous upload {existing_log.id} "
                f"('{existing_log.file_name}'). Pass allow_duplicate=true to override."
            )

        # Store file in UPLOAD_DIR with safe UUID filename
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_saved_name = f"{uuid.uuid4().hex}.{ext}"
        saved_path = upload_dir / safe_saved_name
        saved_path.write_bytes(data)

        # Pure parser execution
        parser = get_parser(declared_type.value)
        parse_result = parser.parse(data)

        # Database matching and cross-validation
        rows = parse_result.rows
        errors = list(parse_result.errors)

        new_count = 0
        update_count = 0

        if declared_type == UploadFileType.STUDENT_LIST:
            new_count, update_count = UploadService._validate_student_list(db, rows, errors)
        elif declared_type == UploadFileType.COURSE_BOOK:
            new_count, update_count = UploadService._validate_course_book(db, rows, errors)
        elif declared_type == UploadFileType.GRADE_CARD:
            new_count, update_count = UploadService._validate_grade_card(
                db, rows, errors, exam_session_id
            )
        elif declared_type == UploadFileType.RESULT:
            new_count, update_count = UploadService._validate_result(
                db, rows, errors, exam_session_id
            )
        elif declared_type == UploadFileType.REVALUATION:
            new_count, update_count = UploadService._validate_revaluation(
                db, rows, errors, exam_session_id
            )

        rows_total = len(rows)
        error_count = len(errors)
        rows_ok = max(0, rows_total - len(set(e.row for e in errors if e.row is not None)))

        summary = {
            "rows_total": rows_total,
            "rows_ok": rows_ok,
            "rows_with_errors": error_count,
            "new": new_count,
            "updates": update_count,
        }

        # Ensure rows_parsed >= rows_failed to satisfy ck_upload_logs_rows_failed_le_parsed
        rows_parsed = max(rows_total, error_count)
        rows_failed = min(rows_parsed, error_count)

        # Persist preview in upload_logs (nothing saved to business tables)
        user_id = getattr(user, "id", None)
        log = UploadRepository.create_log(
            db,
            file_name=safe_base,
            file_type=declared_type,
            uploaded_by=user_id,
            status=UploadStatus.PREVIEW,
            rows_parsed=rows_parsed,
            rows_failed=rows_failed,
            preview_payload={
                "rows": rows,
                "summary": summary,
                "meta": parse_result.meta,
                "warning": warning_msg,
            },
            error_summary=[e.to_dict() for e in errors],
            file_hash=file_hash,
            stored_path=str(saved_path),
            exam_session_id=exam_session_id,
        )

        return {
            "upload_id": log.id,
            "file_type": declared_type.value,
            "summary": summary,
            "sample_rows": rows[:5],
            "errors": [e.to_dict() for e in errors],
            "warning": warning_msg,
        }

    # ----------------------------------------------------------------------- #
    # Validation Helpers for Preview
    # ----------------------------------------------------------------------- #
    @staticmethod
    def _validate_student_list(
        db: Session, rows: list[dict[str, Any]], errors: list[ParseError]
    ) -> tuple[int, int]:
        reg_nos = [r["register_no"] for r in rows if "register_no" in r]
        existing_regs = set(
            db.execute(select(Student.register_no).where(Student.register_no.in_(reg_nos)))
            .scalars()
            .all()
        )
        new_cnt = sum(1 for r in reg_nos if r not in existing_regs)
        upd_cnt = sum(1 for r in reg_nos if r in existing_regs)
        return new_cnt, upd_cnt

    @staticmethod
    def _validate_course_book(
        db: Session, rows: list[dict[str, Any]], errors: list[ParseError]
    ) -> tuple[int, int]:
        ktu_ids = set()
        codes = set()
        for r in rows:
            codes.add(r.get("course_code"))
            for f in r.get("faculty", []):
                if f.get("ktu_id"):
                    ktu_ids.add(f["ktu_id"])

        existing_fac = set(
            db.execute(select(Faculty.ktu_id).where(Faculty.ktu_id.in_(ktu_ids))).scalars().all()
        )
        existing_sub = set(
            db.execute(select(Subject.code).where(Subject.code.in_(codes))).scalars().all()
        )

        new_cnt = sum(1 for k in ktu_ids if k not in existing_fac) + sum(
            1 for c in codes if c not in existing_sub
        )
        upd_cnt = sum(1 for k in ktu_ids if k in existing_fac)
        return new_cnt, upd_cnt

    @staticmethod
    def _validate_grade_card(
        db: Session,
        rows: list[dict[str, Any]],
        errors: list[ParseError],
        exam_session_id: uuid.UUID | None,
    ) -> tuple[int, int]:
        reg_nos = [r["register_no"] for r in rows if "register_no" in r]
        existing_students = dict(
            db.execute(
                select(Student.register_no, Student.id).where(
                    Student.register_no.in_(reg_nos),
                    Student.deleted_at.is_(None),
                )
            ).all()
        )

        # Unknown register number errors
        for r in rows:
            reg = r.get("register_no")
            if reg and reg not in existing_students:
                errors.append(
                    ParseError(
                        page=r.get("page"),
                        row=r.get("row"),
                        code=ErrorCode.UNKNOWN_REGISTER_NO,
                        message=f"Student register number '{reg}' not in master student list",
                    )
                )

        new_cnt = len(rows)
        upd_cnt = 0
        return new_cnt, upd_cnt

    @staticmethod
    def _validate_result(
        db: Session,
        rows: list[dict[str, Any]],
        errors: list[ParseError],
        exam_session_id: uuid.UUID | None,
    ) -> tuple[int, int]:
        reg_nos = {r["register_no"] for r in rows if "register_no" in r}
        existing_students = set(
            db.execute(
                select(Student.register_no).where(
                    Student.register_no.in_(reg_nos),
                    Student.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )

        course_codes = {r["course_code"] for r in rows if "course_code" in r}
        existing_courses = set(
            db.execute(
                select(Subject.code).where(
                    Subject.code.in_(course_codes),
                    Subject.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )

        for r in rows:
            reg = r.get("register_no")
            c_code = r.get("course_code")
            if reg and reg not in existing_students:
                errors.append(
                    ParseError(
                        page=r.get("page"),
                        row=r.get("row", 1),
                        code=ErrorCode.UNKNOWN_REGISTER_NO,
                        message=f"Student register number '{reg}' not in master student list",
                    )
                )
            if c_code and c_code not in existing_courses:
                errors.append(
                    ParseError(
                        page=r.get("page"),
                        row=r.get("row", 1),
                        code=ErrorCode.UNKNOWN_COURSE_CODE,
                        message=f"Course code '{c_code}' not found in course catalogue",
                    )
                )

        return len(rows), 0

    @staticmethod
    def _validate_revaluation(
        db: Session,
        rows: list[dict[str, Any]],
        errors: list[ParseError],
        exam_session_id: uuid.UUID | None,
    ) -> tuple[int, int]:
        return 0, len(rows)

    # ----------------------------------------------------------------------- #
    # Confirm Execution
    # ----------------------------------------------------------------------- #
    @staticmethod
    def confirm_upload(db: Session, user: Any, upload_id: uuid.UUID) -> dict[str, Any]:
        log = UploadRepository.get_by_id(db, upload_id, include_deleted=True)
        if not log:
            raise NotFoundError(f"Upload {upload_id} not found.")

        if log.deleted_at is not None or log.status == UploadStatus.CANCELLED:
            raise ConflictError(f"Upload {upload_id} has been cancelled, cannot confirm.")

        if log.status != UploadStatus.PREVIEW:
            raise ConflictError(
                f"Upload {upload_id} is in status '{log.status.value}', cannot confirm."
            )

        payload = log.preview_payload or {}
        rows = payload.get("rows", [])
        meta = payload.get("meta", {})
        file_type = log.file_type

        # Execute confirmation within a single transaction
        with db.begin_nested():
            if file_type == UploadFileType.STUDENT_LIST:
                applied = UploadService._confirm_student_list(db, rows)
            elif file_type == UploadFileType.COURSE_BOOK:
                applied = UploadService._confirm_course_book(db, rows, meta)
            elif file_type == UploadFileType.GRADE_CARD:
                applied = UploadService._confirm_grade_card(db, rows, meta, log.exam_session_id)
            elif file_type == UploadFileType.RESULT:
                applied = UploadService._confirm_result(db, rows, meta, log.exam_session_id)
            elif file_type == UploadFileType.REVALUATION:
                applied = UploadService._confirm_revaluation(db, rows, log)
            else:
                applied = 0

            log.status = UploadStatus.CONFIRMED
            if applied > log.rows_parsed:
                log.rows_parsed = applied
            db.flush()

        return {
            "upload_id": log.id,
            "status": "confirmed",
            "rows_applied": applied,
            "summary": payload.get("summary"),
        }

    @staticmethod
    def _get_or_create_program(db: Session, code: str) -> Program:
        code_norm = code.upper()
        p = db.execute(select(Program).where(Program.code == code_norm)).scalar_one_or_none()
        if not p:
            names = {
                "CS": "Computer Science and Engineering",
                "CC": "Computer Science and Engineering (Cyber Security)",
                "ME": "Mechanical Engineering",
                "CE": "Civil Engineering",
                "MC": "Mechatronics Engineering",
                "AD": "Artificial Intelligence and Data Science",
            }
            p = Program(code=code_norm, name=names.get(code_norm, code_norm), is_active=True)
            db.add(p)
            db.flush()
        return p

    @staticmethod
    def _get_or_create_batch(db: Session, admission_year: int) -> Batch:
        label = f"{admission_year}-{str(admission_year + 4)[-2:]}"
        b = db.execute(select(Batch).where(Batch.start_year == admission_year)).scalar_one_or_none()
        if not b:
            b = Batch(start_year=admission_year, end_year=admission_year + 4, label=label)
            db.add(b)
            db.flush()
        return b

    @staticmethod
    def _get_or_create_division(
        db: Session, program_id: uuid.UUID, batch_id: uuid.UUID, name: str
    ) -> Division:
        name_clean = name.strip().upper()
        d = db.execute(
            select(Division).where(
                Division.program_id == program_id,
                Division.batch_id == batch_id,
                Division.name == name_clean,
            )
        ).scalar_one_or_none()
        if not d:
            d = Division(program_id=program_id, batch_id=batch_id, name=name_clean)
            db.add(d)
            db.flush()
        return d

    @staticmethod
    def _get_or_create_exam_session(
        db: Session, session_id: uuid.UUID | None, title: str | None = None
    ) -> ExamSession:
        if session_id:
            es = db.execute(
                select(ExamSession).where(ExamSession.id == session_id)
            ).scalar_one_or_none()
            if es:
                return es

        name = title or "Dec 2024"
        es = db.execute(select(ExamSession).where(ExamSession.name == name)).scalar_one_or_none()
        if not es:
            es = ExamSession(name=name, exam_type=ExamType.REGULAR, scheme="2019")
            db.add(es)
            db.flush()
        return es

    @staticmethod
    def _confirm_student_list(db: Session, rows: list[dict[str, Any]]) -> int:
        count = 0
        for r in rows:
            reg = r["register_no"]
            prog = UploadService._get_or_create_program(db, r["program_code"])
            batch = UploadService._get_or_create_batch(db, r["admission_year"])

            div_id = None
            if r.get("division"):
                div = UploadService._get_or_create_division(db, prog.id, batch.id, r["division"])
                div_id = div.id

            student = db.execute(
                select(Student).where(Student.register_no == reg)
            ).scalar_one_or_none()

            if student:
                student.name = r["name"]
                student.program_id = prog.id
                student.batch_id = batch.id
                student.division_id = div_id
                student.is_flagged = r.get("is_flagged", False)
                student.deleted_at = None
            else:
                student = Student(
                    register_no=reg,
                    name=r["name"],
                    program_id=prog.id,
                    batch_id=batch.id,
                    division_id=div_id,
                    is_flagged=r.get("is_flagged", False),
                    status=StudentStatus.ACTIVE,
                )
                db.add(student)
            count += 1
        db.flush()
        return count

    @staticmethod
    def _confirm_course_book(db: Session, rows: list[dict[str, Any]], meta: dict[str, Any]) -> int:
        count = 0
        for r in rows:
            code = r["course_code"]
            name = r["course_name"]
            sem = r.get("semester", 1)
            ay = r.get("academic_year", "2022-23")
            prog_code = r.get("program_code", "CS")
            slot = r.get("slot", "A")

            prog = UploadService._get_or_create_program(db, prog_code)

            # Extract start year for batch from academic year e.g. "2022-23" -> 2022
            m_yr = re.search(r"\d{4}", ay)
            adm_yr = int(m_yr.group()) if m_yr else 2022
            batch = UploadService._get_or_create_batch(db, adm_yr)

            # Get or create subject
            subject = db.execute(
                select(Subject).where(Subject.code == code, Subject.scheme == "2019")
            ).scalar_one_or_none()
            if not subject:
                subject = Subject(
                    code=code,
                    name=name,
                    semester=sem,
                    scheme="2019",
                    type=SubjectType.THEORY,
                )
                db.add(subject)
                db.flush()

            for fac in r.get("faculty", []):
                ktu_id = fac.get("ktu_id")
                fac_name = fac.get("name", "Unknown Faculty")
                phone = fac.get("phone")
                email = fac.get("email")
                part = fac.get("part_label")
                is_main = fac.get("is_main_faculty", True)

                # Upsert faculty
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

                # Upsert CourseOffering
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
                count += 1

        db.flush()
        return count

    @staticmethod
    def _confirm_grade_card(
        db: Session,
        rows: list[dict[str, Any]],
        meta: dict[str, Any],
        session_id: uuid.UUID | None,
    ) -> int:
        es = UploadService._get_or_create_exam_session(db, session_id)
        count = 0

        for r in rows:
            reg = r["register_no"]
            sem = r.get("semester", 1)
            earned_cr = r.get("earned_credits")
            cum_cr = r.get("cumulative_credits")
            sgpa = r.get("sgpa")
            cgpa = r.get("cgpa")

            student = db.execute(
                select(Student).where(Student.register_no == reg)
            ).scalar_one_or_none()
            if not student:
                continue

            # Upsert GradeCard
            gc = db.execute(
                select(GradeCard).where(
                    GradeCard.student_id == student.id,
                    GradeCard.semester == sem,
                    GradeCard.exam_session_id == es.id,
                )
            ).scalar_one_or_none()

            if gc:
                gc.earned_credits = earned_cr
                gc.cumulative_credits = cum_cr
                gc.sgpa = sgpa
                gc.cgpa = cgpa
                gc.deleted_at = None
            else:
                gc = GradeCard(
                    student_id=student.id,
                    semester=sem,
                    exam_session_id=es.id,
                    earned_credits=earned_cr,
                    cumulative_credits=cum_cr,
                    sgpa=sgpa,
                    cgpa=cgpa,
                )
                db.add(gc)

            # Upsert per-course results
            for cr in r.get("course_results", []):
                c_code = cr["course_code"]
                g_str = cr["grade"]
                status_str = cr["status"]

                subject = db.execute(
                    select(Subject).where(Subject.code == c_code, Subject.scheme == "2019")
                ).scalar_one_or_none()
                if not subject:
                    subject = Subject(code=c_code, name=c_code, semester=sem, scheme="2019")
                    db.add(subject)
                    db.flush()

                sr = db.execute(
                    select(SemesterResult).where(
                        SemesterResult.student_id == student.id,
                        SemesterResult.subject_id == subject.id,
                        SemesterResult.exam_session_id == es.id,
                    )
                ).scalar_one_or_none()

                try:
                    grade_enum = Grade(g_str)
                except ValueError:
                    grade_enum = None

                try:
                    status_enum = ResultStatus(status_str)
                except ValueError:
                    status_enum = ResultStatus.PASS

                if sr:
                    sr.grade = grade_enum
                    sr.status = status_enum
                    sr.semester = sem
                    sr.deleted_at = None
                else:
                    sr = SemesterResult(
                        student_id=student.id,
                        subject_id=subject.id,
                        exam_session_id=es.id,
                        semester=sem,
                        grade=grade_enum,
                        status=status_enum,
                        is_regular_attempt=True,
                    )
                    db.add(sr)
            count += 1

        db.flush()
        return count

    @staticmethod
    def _confirm_result(
        db: Session,
        rows: list[dict[str, Any]],
        meta: dict[str, Any],
        session_id: uuid.UUID | None,
    ) -> int:
        title = meta.get("exam_title")
        es = UploadService._get_or_create_exam_session(db, session_id, title)
        count = 0

        for r in rows:
            reg = r["register_no"]
            c_code = r["course_code"]
            grade_str = r["grade"]
            status_str = r["status"]
            sem = r.get("semester", 1)

            student = db.execute(
                select(Student).where(Student.register_no == reg)
            ).scalar_one_or_none()
            if not student:
                continue

            subject = db.execute(
                select(Subject).where(Subject.code == c_code, Subject.scheme == "2019")
            ).scalar_one_or_none()
            if not subject:
                subject = Subject(code=c_code, name=c_code, semester=sem, scheme="2019")
                db.add(subject)
                db.flush()

            sr = db.execute(
                select(SemesterResult).where(
                    SemesterResult.student_id == student.id,
                    SemesterResult.subject_id == subject.id,
                    SemesterResult.exam_session_id == es.id,
                )
            ).scalar_one_or_none()

            try:
                grade_enum = Grade(grade_str)
            except ValueError:
                grade_enum = None

            try:
                status_enum = ResultStatus(status_str)
            except ValueError:
                status_enum = ResultStatus.FAIL

            if sr:
                sr.grade = grade_enum
                sr.status = status_enum
                sr.semester = sem
                sr.deleted_at = None
            else:
                sr = SemesterResult(
                    student_id=student.id,
                    subject_id=subject.id,
                    exam_session_id=es.id,
                    semester=sem,
                    grade=grade_enum,
                    status=status_enum,
                    is_regular_attempt=False,
                )
                db.add(sr)
            count += 1

        db.flush()
        return count

    @staticmethod
    def _confirm_revaluation(db: Session, rows: list[dict[str, Any]], log: UploadLog) -> int:
        count = 0
        for r in rows:
            if r.get("is_no_change"):
                continue

            reg = r["register_no"]
            c_code = r["course_code"]
            new_g_str = r["grade"]
            new_st_str = r["status"]

            student = db.execute(
                select(Student).where(Student.register_no == reg)
            ).scalar_one_or_none()
            if not student:
                continue

            subject = db.execute(
                select(Subject).where(Subject.code == c_code, Subject.scheme == "2019")
            ).scalar_one_or_none()
            if not subject:
                continue

            # Find latest semester result for this student & subject
            sr = (
                db.execute(
                    select(SemesterResult)
                    .where(
                        SemesterResult.student_id == student.id,
                        SemesterResult.subject_id == subject.id,
                        SemesterResult.deleted_at.is_(None),
                    )
                    .order_by(SemesterResult.created_at.desc())
                )
                .scalars()
                .first()
            )

            if not sr:
                continue

            old_grade = sr.grade
            old_status = sr.status

            try:
                new_grade = Grade(new_g_str)
            except ValueError:
                new_grade = old_grade

            try:
                new_status = ResultStatus(new_st_str)
            except ValueError:
                new_status = ResultStatus.PASS

            # Update semester result
            sr.grade = new_grade
            sr.status = new_status

            # Append to ResultHistory
            rh = ResultHistory(
                semester_result_id=sr.id,
                old_grade=old_grade,
                new_grade=new_grade,
                old_status=old_status,
                new_status=new_status,
                change_type=ChangeType.REVALUATION,
                source_upload_id=log.id,
            )
            db.add(rh)
            count += 1

        db.flush()
        return count

    @staticmethod
    def cancel_upload(db: Session, user: Any, upload_id: uuid.UUID) -> dict[str, Any]:
        log = UploadRepository.get_by_id(db, upload_id)
        if not log:
            raise NotFoundError(f"Upload {upload_id} not found.")

        if log.status == UploadStatus.CONFIRMED:
            raise ConflictError("Cannot cancel an upload that has already been confirmed.")

        UploadRepository.soft_delete(db, log)
        return {"upload_id": log.id, "status": "cancelled"}

    @staticmethod
    def list_uploads(
        db: Session,
        user: Any,
        page: int = 1,
        page_size: int = 25,
        file_type: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        items, total = UploadRepository.list_logs(
            db, page=page, page_size=page_size, file_type=file_type, status=status
        )
        return {
            "items": [
                {
                    "id": u.id,
                    "file_name": u.file_name,
                    "file_type": u.file_type.value
                    if hasattr(u.file_type, "value")
                    else str(u.file_type),
                    "uploaded_by": u.uploaded_by,
                    "rows_parsed": u.rows_parsed,
                    "rows_failed": u.rows_failed,
                    "status": u.status.value if hasattr(u.status, "value") else str(u.status),
                    "created_at": u.created_at,
                    "updated_at": u.updated_at,
                }
                for u in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


__all__ = ["UploadService"]
