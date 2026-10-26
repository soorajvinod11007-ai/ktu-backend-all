"""Parser for KTU Result PDFs."""

from __future__ import annotations

import io
import re
from typing import Any

import pdfplumber

from app.common.register_no import parse_register_no
from app.modules.uploads.parsers.base import (
    ABSENT_GRADES,
    FAIL_GRADES,
    PASS_GRADES,
    TBP_GRADES,
    VALID_GRADES,
    WITHHELD_GRADES,
    BaseParser,
    ErrorCode,
    ParseError,
    ParseResult,
    normalize_program_heading,
)

# Regex for register numbers
_REG_RE = re.compile(r"\b([A-Z]{3,5}\d{2}[A-Z]{2}\d{3})\b")

# Regex for course grade pair: e.g. MAT101(F), EST100(Absent), MAT101(No change)
_COURSE_GRADE_RE = re.compile(r"([A-Z]{2,4}\d{3})\s*\(([^)]+)\)")

# Header line pattern for branches/programs
_BRANCH_RE = re.compile(
    r"(?:Branch|Programme|Program)\s*:\s*(.*)|"
    r"^(?:B\.Tech\s+in\s+)?(COMPUTER\s+SCIENCE|MECHANICAL|CIVIL|MECHATRONICS|ARTIFICIAL\s+INTELLIGENCE|CYBER\s+SECURITY)[A-Z\s\(\)&]*$",
    re.IGNORECASE | re.MULTILINE,
)

# Exam title pattern
_EXAM_TITLE_RE = re.compile(r"(B\.Tech.*?Exam.*?20\d{2})", re.IGNORECASE)
_DATE_RE = re.compile(r"Generated\s+(?:on|at)\s*:\s*([0-9\/\-\:\s]+)", re.IGNORECASE)


def infer_semester_from_code(code: str) -> int:
    """Infer semester level from course code digits (e.g. 101 -> 1, 201 -> 3, etc.)."""
    m = re.search(r"\d{3}", code)
    if not m:
        return 1
    digit = int(m.group()[0])
    level_map = {1: 1, 2: 3, 3: 5, 4: 7}
    return level_map.get(digit, 1)


def normalize_grade(grade_str: str) -> tuple[str, str]:
    """Return (canonical_grade, status)."""
    raw = grade_str.strip()
    upper = raw.upper()

    if upper in PASS_GRADES:
        return upper, "pass"
    if upper in FAIL_GRADES:
        return upper, "fail"
    if upper in ABSENT_GRADES:
        return "AB", "absent"
    if upper in WITHHELD_GRADES:
        return "Withheld", "withheld"
    if upper in TBP_GRADES:
        return "TBP", "tbp"
    if upper == "NO CHANGE":
        return "No change", "no_change"

    return raw, "unknown"


class ResultPdfParser(BaseParser):
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
        meta: dict[str, Any] = {"exam_title": None, "generated_on": None, "courses": {}}
        current_program: str | None = None

        total_pages = len(pdf.pages)
        meta["total_pages"] = total_pages

        for page_idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text:
                continue

            # Check for exam title and generated on on early pages
            if not meta["exam_title"]:
                m_title = _EXAM_TITLE_RE.search(text)
                if m_title:
                    meta["exam_title"] = m_title.group(1).strip()
            if not meta["generated_on"]:
                m_date = _DATE_RE.search(text)
                if m_date:
                    meta["generated_on"] = m_date.group(1).strip()

            lines = text.split("\n")
            current_reg: str | None = None
            current_student_courses: list[tuple[str, str]] = []

            def flush_student(p_idx: int, line_no: int, prog: str | None) -> None:
                nonlocal current_reg, current_student_courses
                if not current_reg or not current_student_courses:
                    current_reg = None
                    current_student_courses = []
                    return

                parsed_reg = parse_register_no(current_reg)
                prog_code = prog or (parsed_reg.program_code if parsed_reg else None)

                for course_code, raw_grade in current_student_courses:
                    norm_g, status = normalize_grade(raw_grade)
                    if status == "unknown" or norm_g.upper() not in VALID_GRADES:
                        errors.append(
                            ParseError(
                                page=p_idx,
                                row=line_no,
                                code=ErrorCode.INVALID_GRADE,
                                message=(
                                    f"Invalid grade '{raw_grade}' for student "
                                    f"'{current_reg}' in course '{course_code}'"
                                ),
                            )
                        )
                        continue

                    rows.append(
                        {
                            "register_no": current_reg,
                            "program_code": prog_code,
                            "course_code": course_code,
                            "grade": norm_g,
                            "status": status,
                            "semester": infer_semester_from_code(course_code),
                            "page": p_idx,
                        }
                    )
                current_reg = None
                current_student_courses = []

            for line_idx, line in enumerate(lines, start=1):
                clean_line = line.strip()
                if not clean_line:
                    continue

                # Ignore headers/footers
                if "Controller of Examinations" in clean_line or clean_line.startswith("Page "):
                    continue

                # Check for program / branch heading
                branch_match = _BRANCH_RE.search(clean_line)
                if branch_match:
                    heading_str = branch_match.group(1) or branch_match.group(2) or clean_line
                    code = normalize_program_heading(heading_str)
                    if code:
                        flush_student(page_idx, line_idx, current_program)
                        current_program = code
                    else:
                        errors.append(
                            ParseError(
                                page=page_idx,
                                row=line_idx,
                                code=ErrorCode.UNKNOWN_PROGRAM_HEADING,
                                message=f"Unrecognized program heading: '{heading_str}'",
                            )
                        )
                    continue

                # Check if line has a register number
                reg_match = _REG_RE.search(clean_line)
                if reg_match:
                    flush_student(page_idx, line_idx, current_program)
                    current_reg = reg_match.group(1)
                    parsed_reg = parse_register_no(current_reg)
                    if parsed_reg is None:
                        errors.append(
                            ParseError(
                                page=page_idx,
                                row=line_idx,
                                code=ErrorCode.STRUCTURE_NOT_RECOGNISED,
                                message=f"Malformed register number: '{current_reg}'",
                            )
                        )
                    elif not parsed_reg.is_valid_prefix:
                        errors.append(
                            ParseError(
                                page=page_idx,
                                row=line_idx,
                                code=ErrorCode.ODD_REGISTER_PREFIX,
                                message=(
                                    f"Odd college prefix '{parsed_reg.college_prefix}' "
                                    f"in register '{current_reg}' (flagged)"
                                ),
                            )
                        )

                    # Extract all course(grade) occurrences from line
                    after_reg = clean_line[reg_match.end() :]
                    cg_matches = _COURSE_GRADE_RE.findall(after_reg)
                    current_student_courses.extend(cg_matches)
                else:
                    # Continuation line for the current student
                    cg_matches = _COURSE_GRADE_RE.findall(clean_line)
                    if cg_matches and current_reg:
                        current_student_courses.extend(cg_matches)

            flush_student(page_idx, len(lines), current_program)

        return ParseResult(rows=rows, errors=errors, meta=meta)
