"""Base abstractions, types, and constants for file parsers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# Error codes required by PROJECT_HANDOFF.md
class ErrorCode:
    UNKNOWN_REGISTER_NO = "UNKNOWN_REGISTER_NO"
    ODD_REGISTER_PREFIX = "ODD_REGISTER_PREFIX"
    UNKNOWN_COURSE_CODE = "UNKNOWN_COURSE_CODE"
    INVALID_GRADE = "INVALID_GRADE"
    UNKNOWN_PROGRAM_HEADING = "UNKNOWN_PROGRAM_HEADING"
    DUPLICATE_ROW = "DUPLICATE_ROW"
    MISSING_FACULTY = "MISSING_FACULTY"
    STRUCTURE_NOT_RECOGNISED = "STRUCTURE_NOT_RECOGNISED"
    WRONG_FILE_TYPE = "WRONG_FILE_TYPE"
    MISSING_DIVISION = "MISSING_DIVISION"


VALID_GRADES = frozenset(
    {
        "S",
        "A+",
        "A",
        "B+",
        "B",
        "C+",
        "C",
        "D",
        "P",
        "F",
        "FE",
        "AB",
        "ABSENT",
        "WITHHELD",
        "TBP",
        "NO CHANGE",
    }
)

PASS_GRADES = frozenset({"S", "A+", "A", "B+", "B", "C+", "C", "D", "P"})
FAIL_GRADES = frozenset({"F", "FE"})
ABSENT_GRADES = frozenset({"AB", "ABSENT"})
WITHHELD_GRADES = frozenset({"WITHHELD"})
TBP_GRADES = frozenset({"TBP"})

# Normalize program headings found in KTU PDFs
_PROGRAM_MAPPINGS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"CYBER\s+SECURITY", re.IGNORECASE), "CC"),
    (re.compile(r"ARTIFICIAL\s+INTELLIGENCE", re.IGNORECASE), "AD"),
    (re.compile(r"MECHATRONICS", re.IGNORECASE), "MC"),
    (re.compile(r"COMPUTER\s+SCIENCE", re.IGNORECASE), "CS"),
    (re.compile(r"MECHANICAL", re.IGNORECASE), "ME"),
    (re.compile(r"CIVIL", re.IGNORECASE), "CE"),
]


def normalize_program_heading(heading: str) -> str | None:
    """Map human or PDF program string to 2-letter program code (CS, ME, MC, CE, AD, CC)."""
    clean = re.sub(r"\s+", " ", heading or "").strip().upper()
    if clean in {"CS", "ME", "MC", "CE", "AD", "CC"}:
        return clean
    for pattern, code in _PROGRAM_MAPPINGS:
        if pattern.search(clean):
            return code
    return None


def normalize_grade(grade_str: str) -> tuple[str, str]:
    """Return (canonical_grade, status)."""
    raw = (grade_str or "").strip()
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


@dataclass
class ParseError:
    page: int | None
    row: int | None
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "row": self.row,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class ParseResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_bytes: bytes, **kwargs: Any) -> ParseResult:
        """Parse raw file bytes into a ParseResult (pure, no DB interaction)."""
        pass
