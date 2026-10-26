"""Parser for KTU Course Book PDFs."""

from __future__ import annotations

import io
import re
from typing import Any

import pdfplumber

from app.modules.uploads.parsers.base import (
    BaseParser,
    ErrorCode,
    ParseError,
    ParseResult,
    normalize_program_heading,
)

_SEM_RE = re.compile(r"Semester\s*:\s*(?:S)?(\d)", re.IGNORECASE)
_AY_RE = re.compile(r"Academic\s+Year\s*:\s*(\d{4}\s*-\s*\d{2,4})", re.IGNORECASE)
_BRANCH_RE = re.compile(r"(?:Branch|Programme|Program)\s*:\s*([^\n\r]+)", re.IGNORECASE)
_SLOT_LINE_RE = re.compile(
    r"Slot\s+([A-Z0-9]+)\s*(?:[-:]?\s*Course\s*(?:Code)?\s*:\s*|\s*[-:]\s*)([A-Z]{2,4}\d{3})\s*[-:]?\s*([^\n\r]+)?",
    re.IGNORECASE,
)
_SLOT_ONLY_RE = re.compile(r"Slot\s+([A-Z0-9]+)", re.IGNORECASE)
_COURSE_ONLY_RE = re.compile(
    r"Course\s*(?:Code)?\s*:\s*([A-Z]{2,4}\d{3})\s*[-:]?\s*([^\n\r]+)?", re.IGNORECASE
)
_FACULTY_NAME_ID_RE = re.compile(r"^(.*?)\s*\((KTU-[A-Za-z0-9]+|KTU[0-9]+)\)", re.IGNORECASE)


def normalize_academic_year(ay_str: str) -> str:
    """Normalize '2022-2023' or '2022 - 23' to '2022-23'."""
    clean = re.sub(r"\s+", "", ay_str)
    parts = clean.split("-")
    if len(parts) == 2:
        start = parts[0]
        end = parts[1][-2:]
        return f"{start}-{end}"
    return clean


class CourseBookPdfParser(BaseParser):
    def parse(self, file_bytes: bytes, **kwargs: Any) -> ParseResult:
        try:
            pdf = pdfplumber.open(io.BytesIO(file_bytes))
        except Exception as exc:
            return ParseResult(
                errors=[
                    ParseError(
                        page=1,
                        row=1,
                        code=ErrorCode.STRUCTURE_NOT_RECOGNISED,
                        message=f"Unable to open PDF document: {exc}",
                    )
                ]
            )

        rows: list[dict[str, Any]] = []
        errors: list[ParseError] = []
        meta: dict[str, Any] = {
            "branch": None,
            "program_code": None,
            "semester": None,
            "academic_year": None,
        }

        # Extract header metadata
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not meta["semester"]:
                m_sem = _SEM_RE.search(text)
                if m_sem:
                    meta["semester"] = int(m_sem.group(1))
            if not meta["academic_year"]:
                m_ay = _AY_RE.search(text)
                if m_ay:
                    meta["academic_year"] = normalize_academic_year(m_ay.group(1))
            if not meta["branch"]:
                m_br = _BRANCH_RE.search(text)
                if m_br:
                    branch_raw = m_br.group(1).strip()
                    meta["branch"] = branch_raw
                    meta["program_code"] = normalize_program_heading(branch_raw)

        default_sem = meta["semester"] or 1
        default_ay = meta["academic_year"] or "2022-23"
        default_prog = meta["program_code"] or "CS"

        for page_idx, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            if tables:
                self._parse_tables_page(
                    tables, page_idx, default_sem, default_ay, default_prog, rows, errors
                )
            else:
                self._parse_text_page(
                    page, page_idx, default_sem, default_ay, default_prog, rows, errors
                )

        return ParseResult(rows=rows, errors=errors, meta=meta)

    def _parse_tables_page(
        self,
        tables: list[list[list[Any]]],
        page_idx: int,
        default_sem: int,
        default_ay: str,
        default_prog: str,
        rows: list[dict[str, Any]],
        errors: list[ParseError],
    ) -> None:
        for table in tables:
            if not table or len(table) < 2:
                continue

            header = [re.sub(r"\s+", " ", str(c or "")).upper().strip() for c in table[0]]
            fac_name_idx = None
            contact_idx = None
            email_idx = None
            batch_idx = None
            main_fac_idx = None

            for i, h in enumerate(header):
                if "FACULTY" in h or "NAME" in h:
                    fac_name_idx = i
                elif "CONTACT" in h or "PHONE" in h:
                    contact_idx = i
                elif "EMAIL" in h:
                    email_idx = i
                elif "BATCH" in h:
                    batch_idx = i
                elif "MAIN" in h:
                    main_fac_idx = i

            if fac_name_idx is None:
                continue

            faculty_entries: list[dict[str, Any]] = []
            for r_idx in range(1, len(table)):
                row = table[r_idx]
                if not row or all(c is None or str(c).strip() == "" for c in row):
                    continue
                raw_fac = re.sub(r"\s+", " ", str(row[fac_name_idx] or "")).strip()
                if not raw_fac:
                    continue

                m_fid = _FACULTY_NAME_ID_RE.search(raw_fac)
                if m_fid:
                    fac_name = m_fid.group(1).strip()
                    ktu_id = m_fid.group(2).strip()
                else:
                    fac_name = raw_fac
                    ktu_id = None

                phone = (
                    re.sub(r"\s+", "", str(row[contact_idx] or ""))
                    if contact_idx is not None and contact_idx < len(row)
                    else None
                )
                email = (
                    re.sub(r"\s+", "", str(row[email_idx] or "")).lower()
                    if email_idx is not None and email_idx < len(row)
                    else None
                )
                batch_str = (
                    str(row[batch_idx] or "").strip()
                    if batch_idx is not None and batch_idx < len(row)
                    else ""
                )
                main_str = (
                    str(row[main_fac_idx] or "").strip().lower()
                    if main_fac_idx is not None and main_fac_idx < len(row)
                    else "yes"
                )
                is_main = "no" not in main_str

                faculty_entries.append(
                    {
                        "name": fac_name,
                        "ktu_id": ktu_id,
                        "phone": phone or None,
                        "email": email or None,
                        "batch": batch_str,
                        "is_main_faculty": is_main,
                    }
                )

            self._assign_part_labels(faculty_entries)
            rows.append(
                {
                    "slot": "A",
                    "course_code": "UNKNOWN",
                    "course_name": "Course",
                    "semester": default_sem,
                    "academic_year": default_ay,
                    "program_code": default_prog,
                    "faculty": faculty_entries,
                    "page": page_idx,
                }
            )

    def _parse_text_page(
        self,
        page: Any,
        page_idx: int,
        default_sem: int,
        default_ay: str,
        default_prog: str,
        rows: list[dict[str, Any]],
        errors: list[ParseError],
    ) -> None:
        text = page.extract_text() or ""
        lines = text.split("\n")

        current_slot: str | None = None
        current_code: str | None = None
        current_name: str | None = None
        current_faculty: list[dict[str, Any]] = []

        def flush():
            nonlocal current_slot, current_code, current_name, current_faculty
            if not current_code:
                return

            self._assign_part_labels(current_faculty)
            if not current_faculty:
                errors.append(
                    ParseError(
                        page=page_idx,
                        row=1,
                        code=ErrorCode.MISSING_FACULTY,
                        message=(
                            f"Missing faculty table for course '{current_code}' "
                            f"in slot '{current_slot}'"
                        ),
                    )
                )

            rows.append(
                {
                    "slot": current_slot or "A",
                    "course_code": current_code,
                    "course_name": current_name or current_code,
                    "semester": default_sem,
                    "academic_year": default_ay,
                    "program_code": default_prog,
                    "faculty": current_faculty,
                    "page": page_idx,
                }
            )
            current_slot = None
            current_code = None
            current_name = None
            current_faculty = []

        for line in lines:
            clean = line.strip()
            if not clean:
                continue

            # Check if line defines a slot and course
            m_sc = _SLOT_LINE_RE.search(clean)
            if m_sc:
                flush()
                current_slot = m_sc.group(1).upper()
                current_code = m_sc.group(2).upper()
                current_name = (m_sc.group(3) or "").strip()
                continue

            m_slot = _SLOT_ONLY_RE.search(clean)
            m_course = _COURSE_ONLY_RE.search(clean)
            if m_slot and m_course:
                flush()
                current_slot = m_slot.group(1).upper()
                current_code = m_course.group(1).upper()
                current_name = (m_course.group(2) or "").strip()
                continue
            elif m_slot:
                flush()
                current_slot = m_slot.group(1).upper()
                continue
            elif m_course:
                current_code = m_course.group(1).upper()
                current_name = (m_course.group(2) or "").strip()
                continue

            # Check if line contains a faculty entry
            m_fac = _FACULTY_NAME_ID_RE.search(clean)
            if m_fac:
                fac_name = m_fac.group(1).strip()
                ktu_id = m_fac.group(2).strip()

                rest = clean[m_fac.end() :].strip().split()
                phone = rest[0] if len(rest) > 0 else None
                email = rest[1] if len(rest) > 1 else None
                batch = rest[2] if len(rest) > 2 else ""
                main_str = rest[3].lower() if len(rest) > 3 else "yes"
                is_main = "no" not in main_str

                current_faculty.append(
                    {
                        "name": fac_name,
                        "ktu_id": ktu_id,
                        "phone": phone,
                        "email": email,
                        "batch": batch,
                        "is_main_faculty": is_main,
                    }
                )

        flush()

    def _assign_part_labels(self, faculty_entries: list[dict[str, Any]]) -> None:
        if len(faculty_entries) == 2:
            faculty_entries[0]["part_label"] = "Part I"
            faculty_entries[1]["part_label"] = "Part II"
        elif len(faculty_entries) > 2:
            for i, f in enumerate(faculty_entries, start=1):
                f["part_label"] = f"Part {i}"
        elif len(faculty_entries) == 1:
            faculty_entries[0]["part_label"] = None
