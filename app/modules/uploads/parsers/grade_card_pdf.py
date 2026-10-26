"""Parser for KTU Semester Grade Card Report PDFs."""

from __future__ import annotations

import io
import re
from typing import Any

import pdfplumber

from app.common.register_no import parse_register_no
from app.modules.uploads.parsers.base import (
    VALID_GRADES,
    BaseParser,
    ErrorCode,
    ParseError,
    ParseResult,
    normalize_grade,
    normalize_program_heading,
)

_SEM_RE = re.compile(r"Semester\s*:\s*(?:S)?(\d)", re.IGNORECASE)
_BRANCH_RE = re.compile(r"(?:Branch|Programme|Program)\s*:\s*([^\n\r]+)", re.IGNORECASE)
_STUDENT_CELL_RE = re.compile(r"([A-Z]{3,5}\d{2}[A-Z]{2}\d{3})\s*-\s*(.*)", re.DOTALL)
_COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,4}\d{3})\b")


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val)).strip()


class GradeCardPdfParser(BaseParser):
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
            "courses": {},
        }

        # Page 1: extract header meta
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not meta["semester"]:
                m_sem = _SEM_RE.search(text)
                if m_sem:
                    meta["semester"] = int(m_sem.group(1))
            if not meta["branch"]:
                m_br = _BRANCH_RE.search(text)
                if m_br:
                    branch_str = m_br.group(1).strip()
                    meta["branch"] = branch_str
                    meta["program_code"] = normalize_program_heading(branch_str)

            # Extract course code - title legend if present
            for m in re.finditer(r"\b([A-Z]{2,4}\d{3})\s*[-:]\s*([^\n\r]+)", text):
                code = m.group(1).strip()
                title = m.group(2).strip()
                if len(title) > 3 and not title.isupper():
                    meta["courses"][code] = title.upper()
                elif len(title) > 3:
                    meta["courses"][code] = title

        default_sem = meta["semester"] or 1

        for page_idx, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            if not tables:
                # Text fallback if no tables extracted
                self._parse_text_fallback(page, page_idx, default_sem, meta, rows, errors)
                continue

            for table in tables:
                if not table or len(table) < 2:
                    continue

                # Process headers
                # Grade card headers may span 1 or 2 rows (wrapped course headers e.g. MAT10 and 1)
                header_row_idx = 0
                course_cols: dict[int, str] = {}
                student_col_idx: int | None = None
                earned_col_idx: int | None = None
                cumulative_col_idx: int | None = None
                sgpa_col_idx: int | None = None
                cgpa_col_idx: int | None = None

                # Find which row has "Student"
                for r_idx in range(min(3, len(table))):
                    row = table[r_idx]
                    joined = " ".join(_clean_str(c).upper() for c in row)
                    if "STUDENT" in joined or "REG" in joined:
                        header_row_idx = r_idx
                        break

                h1 = table[header_row_idx]
                h2 = table[header_row_idx + 1] if header_row_idx + 1 < len(table) else None

                # Merge multi-line header cells if course code wraps
                for col_idx, cell1 in enumerate(h1):
                    val1 = _clean_str(cell1).upper()
                    val2 = _clean_str(h2[col_idx]).upper() if (h2 and col_idx < len(h2)) else ""
                    combined = f"{val1}{val2}".replace(" ", "")

                    if "STUDENT" in val1 or "STUDENT" in combined:
                        student_col_idx = col_idx
                    elif "EARNED" in val1 or "EARNED" in combined:
                        earned_col_idx = col_idx
                    elif "CUMULATIVE" in val1 or "CUMULATIVE" in combined:
                        cumulative_col_idx = col_idx
                    elif "SGPA" in val1 or "SGPA" in combined:
                        sgpa_col_idx = col_idx
                    elif "CGPA" in val1 or "CGPA" in combined:
                        cgpa_col_idx = col_idx
                    else:
                        m_code = _COURSE_CODE_RE.search(combined) or _COURSE_CODE_RE.search(val1)
                        if m_code:
                            course_cols[col_idx] = m_code.group(1)

                data_start_idx = header_row_idx + (2 if h2 and course_cols else 1)

                for r_idx in range(data_start_idx, len(table)):
                    row = table[r_idx]
                    if not row or all(c is None or str(c).strip() == "" for c in row):
                        continue

                    # Extract student cell
                    st_val = (
                        _clean_str(row[student_col_idx])
                        if student_col_idx is not None and student_col_idx < len(row)
                        else ""
                    )
                    m_st = _STUDENT_CELL_RE.search(st_val)
                    if not m_st:
                        # Maybe line wrapped or not a student row
                        continue

                    reg_raw = m_st.group(1).strip()
                    name_raw = re.sub(r"\s+", " ", m_st.group(2)).strip()

                    parsed_reg = parse_register_no(reg_raw)
                    if parsed_reg is None:
                        errors.append(
                            ParseError(
                                page=page_idx,
                                row=r_idx + 1,
                                code=ErrorCode.STRUCTURE_NOT_RECOGNISED,
                                message=f"Invalid register number: '{reg_raw}'",
                            )
                        )
                        continue
                    if not parsed_reg.is_valid_prefix:
                        errors.append(
                            ParseError(
                                page=page_idx,
                                row=r_idx + 1,
                                code=ErrorCode.ODD_REGISTER_PREFIX,
                                message=(
                                    f"Odd college prefix '{parsed_reg.college_prefix}' for "
                                    f"student '{reg_raw}' (flagged)"
                                ),
                            )
                        )

                    # Extract SGPA, CGPA, Credits
                    def parse_float(val: Any) -> float | None:
                        try:
                            s = _clean_str(val).replace(",", ".")
                            return float(s) if s and s != "-" else None
                        except Exception:
                            return None

                    def parse_int(val: Any) -> int | None:
                        try:
                            s = _clean_str(val)
                            return int(float(s)) if s and s != "-" else None
                        except Exception:
                            return None

                    earned_cr = (
                        parse_int(row[earned_col_idx])
                        if earned_col_idx is not None and earned_col_idx < len(row)
                        else None
                    )
                    cum_cr = (
                        parse_int(row[cumulative_col_idx])
                        if cumulative_col_idx is not None and cumulative_col_idx < len(row)
                        else None
                    )
                    sgpa = (
                        parse_float(row[sgpa_col_idx])
                        if sgpa_col_idx is not None and sgpa_col_idx < len(row)
                        else None
                    )
                    cgpa = (
                        parse_float(row[cgpa_col_idx])
                        if cgpa_col_idx is not None and cgpa_col_idx < len(row)
                        else None
                    )

                    # Extract per-course grades
                    course_results: list[dict[str, Any]] = []
                    for c_idx, c_code in course_cols.items():
                        if c_idx >= len(row):
                            continue
                        g_cell = _clean_str(row[c_idx])
                        if not g_cell or g_cell in {"-", "NA", "N/A"}:
                            # Blank or not taken
                            continue

                        norm_g, status = normalize_grade(g_cell)
                        if norm_g.upper() not in VALID_GRADES:
                            errors.append(
                                ParseError(
                                    page=page_idx,
                                    row=r_idx + 1,
                                    code=ErrorCode.INVALID_GRADE,
                                    message=(
                                        f"Invalid grade '{g_cell}' for student "
                                        f"'{reg_raw}' in '{c_code}'"
                                    ),
                                )
                            )
                            continue

                        course_results.append(
                            {
                                "course_code": c_code,
                                "grade": norm_g,
                                "status": status,
                                "semester": default_sem,
                            }
                        )

                    rows.append(
                        {
                            "register_no": reg_raw,
                            "name": name_raw,
                            "program_code": meta["program_code"] or parsed_reg.program_code,
                            "semester": default_sem,
                            "earned_credits": earned_cr,
                            "cumulative_credits": cum_cr,
                            "sgpa": sgpa,
                            "cgpa": cgpa,
                            "course_results": course_results,
                            "page": page_idx,
                            "row": r_idx + 1,
                        }
                    )

        return ParseResult(rows=rows, errors=errors, meta=meta)

    def _parse_text_fallback(
        self,
        page: Any,
        page_idx: int,
        default_sem: int,
        meta: dict[str, Any],
        rows: list[dict[str, Any]],
        errors: list[ParseError],
    ) -> None:
        text = page.extract_text() or ""
        lines = text.split("\n")

        # Discover course codes from header lines or legend
        course_codes = list(meta.get("courses", {}).keys())
        if not course_codes:
            for line in lines:
                codes = _COURSE_CODE_RE.findall(line)
                if codes and any(
                    c in line.upper()
                    for c in ("STUDENT", "EARNED", "SGPA", "MAT", "CST", "EST", "CYT")
                ):
                    course_codes = codes
                    break

        for line_no, line in enumerate(lines, start=1):
            m_st = _STUDENT_CELL_RE.search(line)
            if not m_st:
                continue

            reg_raw = m_st.group(1).strip()
            rest = m_st.group(2).strip()

            parsed_reg = parse_register_no(reg_raw)
            if not parsed_reg:
                continue

            # Tokenize rest from right to left:
            # [name words...] [grades...] [earned] [cum] [sgpa] [cgpa]
            tokens = rest.split()
            cgpa = None
            sgpa = None
            earned_cr = None
            cum_cr = None

            # Attempt to parse float/int numbers from right
            idx = len(tokens) - 1
            if idx >= 0 and re.match(r"^\d+(\.\d+)?$", tokens[idx]):
                try:
                    cgpa = float(tokens[idx])
                    idx -= 1
                except ValueError:
                    pass
            if idx >= 0 and re.match(r"^\d+(\.\d+)?$", tokens[idx]):
                try:
                    sgpa = float(tokens[idx])
                    idx -= 1
                except ValueError:
                    pass
            if idx >= 0 and re.match(r"^\d+$", tokens[idx]):
                try:
                    cum_cr = int(tokens[idx])
                    idx -= 1
                except ValueError:
                    pass
            if idx >= 0 and re.match(r"^\d+$", tokens[idx]):
                try:
                    earned_cr = int(tokens[idx])
                    idx -= 1
                except ValueError:
                    pass

            # Remaining tokens: name + grades
            # Course grades matching course_codes from right
            course_results: list[dict[str, Any]] = []
            num_courses = len(course_codes)
            if num_courses > 0 and idx >= num_courses:
                grade_tokens = tokens[idx - num_courses + 1 : idx + 1]
                name_tokens = tokens[: idx - num_courses + 1]
                name_raw = " ".join(name_tokens).strip()

                for c_code, g_token in zip(course_codes, grade_tokens, strict=False):
                    norm_g, status = normalize_grade(g_token)
                    if norm_g.upper() in VALID_GRADES:
                        course_results.append(
                            {
                                "course_code": c_code,
                                "grade": norm_g,
                                "status": status,
                                "semester": default_sem,
                            }
                        )
            else:
                name_raw = " ".join(tokens[: idx + 1]).strip()

            rows.append(
                {
                    "register_no": reg_raw,
                    "name": name_raw or reg_raw,
                    "program_code": meta["program_code"] or parsed_reg.program_code,
                    "semester": default_sem,
                    "earned_credits": earned_cr,
                    "cumulative_credits": cum_cr,
                    "sgpa": sgpa,
                    "cgpa": cgpa,
                    "course_results": course_results,
                    "page": page_idx,
                    "row": line_no,
                }
            )
