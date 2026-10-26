# results/models
"""ExamSession, SemesterResult, ResultHistory, GradeCard.

SemesterResult deliberately has no batch_id column: a backlog student from an
older batch may appear in a newer exam session, so the only stable link is
student_id. Batch/program/division for reporting are reached by joining
SemesterResult -> Student.

ResultHistory records both revaluation changes (old_grade -> new_grade) and
supply re-registration events. "No change" is a revaluation-only outcome and is
never stored as a Grade; it is represented by old_grade == new_grade.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.base import TimestampMixin
from app.core.database import Base

if TYPE_CHECKING:
    # Only for type checkers. Runtime resolution uses the SQLAlchemy registry.
    from app.modules.students.models import Student
    from app.modules.faculty.models import Subject


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class ExamType(str, enum.Enum):
    REGULAR = "regular"
    SUPPLEMENTARY = "supplementary"


class Grade(str, enum.Enum):
    """KTU grades. Absent = "AB"; Withheld and TBP are placeholders, not marks.

    "No change" is deliberately absent: it is a revaluation decision, not a grade,
    and is represented in ResultHistory by old_grade == new_grade.
    """

    S = "S"
    A_PLUS = "A+"
    A = "A"
    B_PLUS = "B+"
    B = "B"
    C_PLUS = "C+"
    C = "C"
    D = "D"
    P = "P"
    F = "F"
    FE = "FE"
    AB = "AB"
    WITHHELD = "Withheld"
    TBP = "TBP"


class ResultStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    ABSENT = "absent"
    WITHHELD = "withheld"
    TBP = "tbp"


class ChangeType(str, enum.Enum):
    REVALUATION = "revaluation"
    SUPPLY = "supply"
    MANUAL_EDIT = "manual_edit"


# Alias for backward-compat and admin resource imports.
ResultChangeType = ChangeType


# Small helpers to keep the SAEnum definitions DRY and lowercase-consistent.
def _sa_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda c: [m.value for m in c],
    )


# --------------------------------------------------------------------------- #
# ExamSession
# --------------------------------------------------------------------------- #
class ExamSession(TimestampMixin, Base):
    __tablename__ = "exam_sessions"

    # Human label as it appears on the PDF, e.g. "Dec 2024", "May 2025".
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    exam_type: Mapped[ExamType] = mapped_column(
        _sa_enum(ExamType, "exam_type"),
        nullable=False,
        default=ExamType.REGULAR,
        server_default=ExamType.REGULAR.value,
    )
    scheme: Mapped[str] = mapped_column(String(8), nullable=False)
    published_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index("ix_exam_sessions_type_published", "exam_type", "published_on"),
    )

    semester_results: Mapped[list["SemesterResult"]] = relationship(
        back_populates="exam_session"
    )
    grade_cards: Mapped[list["GradeCard"]] = relationship(
        back_populates="exam_session"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ExamSession {self.name} type={self.exam_type.value}>"


# --------------------------------------------------------------------------- #
# SemesterResult
# --------------------------------------------------------------------------- #
class SemesterResult(TimestampMixin, Base):
    """One row per (student, subject, exam_session).

    The unique constraint is the natural key that result/revaluation PDFs key on;
    re-ingesting the same session updates in place rather than duplicating.
    """

    __tablename__ = "semester_results"

    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("students.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subjects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    exam_session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("exam_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Curriculum semester of the subject (1-8), independent of when the exam ran.
    semester: Mapped[int] = mapped_column(Integer, nullable=False)

    # Nullable: absent / withheld / TBP rows may have no grade at all.
    grade: Mapped[Grade | None] = mapped_column(_sa_enum(Grade, "grade"), nullable=True)
    status: Mapped[ResultStatus] = mapped_column(
        _sa_enum(ResultStatus, "result_status"), nullable=False
    )

    # True when this was the student's first sitting (regular exam), False for
    # supply/improvement attempts.
    is_regular_attempt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id", "subject_id", "exam_session_id",
            name="uq_semester_results_natural_key",
        ),
        CheckConstraint("semester BETWEEN 1 AND 8", name="semester_range"),
        # "Course-wise faculty-wise performance" scans by subject within a session.
        Index("ix_semester_results_subject_session", "subject_id", "exam_session_id"),
        # "Program/semester-wise pass %": filter by semester, join to student for batch/program.
        Index("ix_semester_results_semester_status", "semester", "status"),
    )

    student: Mapped["Student"] = relationship(backref="semester_results")
    subject: Mapped["Subject"] = relationship(backref="semester_results")
    exam_session: Mapped[ExamSession] = relationship(back_populates="semester_results")

    history: Mapped[list["ResultHistory"]] = relationship(
        back_populates="semester_result",
        order_by="ResultHistory.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SemesterResult student={self.student_id} subject={self.subject_id} "
            f"session={self.exam_session_id} status={self.status.value}>"
        )


# --------------------------------------------------------------------------- #
# ResultHistory
# --------------------------------------------------------------------------- #
class ResultHistory(TimestampMixin, Base):
    """Append-only log of grade/status changes for one SemesterResult.

    Rows are never edited: a revaluation that changes A -> A+ writes one row with
    change_type=revaluation; a revaluation that changes nothing writes a row with
    old_grade == new_grade (the "no change" outcome).
    """

    __tablename__ = "result_history"

    semester_result_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("semester_results.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    old_grade: Mapped[Grade | None] = mapped_column(_sa_enum(Grade, "grade"), nullable=True)
    new_grade: Mapped[Grade | None] = mapped_column(_sa_enum(Grade, "grade"), nullable=True)
    old_status: Mapped[ResultStatus | None] = mapped_column(
        _sa_enum(ResultStatus, "result_status"), nullable=True
    )
    new_status: Mapped[ResultStatus | None] = mapped_column(
        _sa_enum(ResultStatus, "result_status"), nullable=True
    )

    change_type: Mapped[ChangeType] = mapped_column(
        _sa_enum(ChangeType, "change_type"), nullable=False
    )

    # FK to upload_logs.id is added by the Part 4 migration. Kept FK-free here so
    # Part 3 can autogenerate before Part 4 exists.
    source_upload_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("upload_logs.id", ondelete="RESTRICT"),
        nullable=True,
    )

    semester_result: Mapped[SemesterResult] = relationship(back_populates="history")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ResultHistory sr={self.semester_result_id} "
            f"type={self.change_type.value}>"
        )


# --------------------------------------------------------------------------- #
# GradeCard
# --------------------------------------------------------------------------- #
class GradeCard(TimestampMixin, Base):
    """Per-student, per-semester, per-session aggregate printed on the grade card."""

    __tablename__ = "grade_cards"

    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("students.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    exam_session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("exam_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )

    earned_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cumulative_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sgpa: Mapped[float | None] = mapped_column(nullable=True)
    cgpa: Mapped[float | None] = mapped_column(nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "student_id", "semester", "exam_session_id",
            name="uq_grade_cards_natural_key",
        ),
        CheckConstraint("semester BETWEEN 1 AND 8", name="semester_range"),
        CheckConstraint("sgpa IS NULL OR (sgpa >= 0 AND sgpa <= 10)", name="sgpa_range"),
        CheckConstraint("cgpa IS NULL OR (cgpa >= 0 AND cgpa <= 10)", name="cgpa_range"),
        CheckConstraint(
            "earned_credits IS NULL OR earned_credits >= 0",
            name="earned_credits_non_negative",
        ),
        CheckConstraint(
            "cumulative_credits IS NULL OR cumulative_credits >= 0",
            name="cumulative_credits_non_negative",
        ),
    )

    student: Mapped["Student"] = relationship(backref="grade_cards")
    exam_session: Mapped[ExamSession] = relationship(back_populates="grade_cards")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GradeCard student={self.student_id} sem={self.semester}>"


__all__ = [
    "ExamSession", "ExamType",
    "SemesterResult", "ResultStatus", "Grade",
    "ResultHistory", "ChangeType", "ResultChangeType",
    "GradeCard",
]