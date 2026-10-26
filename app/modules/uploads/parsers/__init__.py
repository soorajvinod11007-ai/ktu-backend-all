"""Parsers package: exposes parser registry and factory."""

from __future__ import annotations

from app.modules.uploads.parsers.base import (
    BaseParser,
    ErrorCode,
    ParseError,
    ParseResult,
    normalize_program_heading,
)
from app.modules.uploads.parsers.course_book_pdf import CourseBookPdfParser
from app.modules.uploads.parsers.detector import detect_file_type
from app.modules.uploads.parsers.grade_card_pdf import GradeCardPdfParser
from app.modules.uploads.parsers.result_pdf import ResultPdfParser
from app.modules.uploads.parsers.revaluation_pdf import RevaluationPdfParser
from app.modules.uploads.parsers.student_list import StudentListParser

_PARSERS: dict[str, type[BaseParser]] = {
    "student_list": StudentListParser,
    "course_book": CourseBookPdfParser,
    "grade_card": GradeCardPdfParser,
    "result": ResultPdfParser,
    "revaluation": RevaluationPdfParser,
}


def get_parser(file_type: str) -> BaseParser:
    """Return a parser instance for the given file type."""
    cls = _PARSERS.get(file_type.lower())
    if not cls:
        raise ValueError(f"No parser registered for file_type '{file_type}'")
    return cls()


__all__ = [
    "BaseParser",
    "ParseError",
    "ParseResult",
    "ErrorCode",
    "StudentListParser",
    "ResultPdfParser",
    "RevaluationPdfParser",
    "GradeCardPdfParser",
    "CourseBookPdfParser",
    "detect_file_type",
    "get_parser",
    "normalize_program_heading",
]
