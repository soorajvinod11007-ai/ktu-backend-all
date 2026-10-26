"""Content-based file type detection for uploaded documents."""

from __future__ import annotations

import io

import pdfplumber


def detect_file_type(data: bytes) -> str | None:
    """Inspect raw file bytes to infer declared file type.

    Returns one of: 'student_list', 'course_book', 'grade_card', 'result', 'revaluation', or None.
    """
    if not data:
        return None

    # Check for Excel / zip magic bytes
    if data.startswith(b"PK\x03\x04") or data.startswith(b"\xd0\xcf\x11\xe0"):
        return "student_list"

    # Check for PDF magic
    if data.startswith(b"%PDF-"):
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                sample_text = ""
                for p in pdf.pages[:3]:
                    sample_text += (p.extract_text() or "") + "\n"

                clean = sample_text.upper()
                if "REVALUATION RESULT" in clean or "REVALUATION" in clean:
                    return "revaluation"
                if "COURSE BOOK DETAILS" in clean or "COURSE BOOK" in clean:
                    return "course_book"
                if (
                    "SEMESTER GRADE CARD" in clean
                    or "GRADE CARD REPORT" in clean
                    or "SGPA" in clean
                ):
                    return "grade_card"
                if (
                    "EXAM CENTRE" in clean
                    or "CONTROLLER OF EXAMINATIONS" in clean
                    or "B.TECH" in clean
                ):
                    return "result"
                return "result"
        except Exception:
            # Fall back to raw string search in PDF stream
            raw_sample = data[:8192].decode("latin-1", errors="ignore").upper()
            if "REVALUATION" in raw_sample:
                return "revaluation"
            if "COURSE BOOK" in raw_sample:
                return "course_book"
            if "GRADE CARD" in raw_sample:
                return "grade_card"
            return "result"

    return None
