# faculty/models
"""Faculty, Subject (course), and CourseOffering.

CourseOffering is where the "one course, two faculty (Part I / Part II)" reality
lives: a single (subject, batch, division, academic_year, semester, slot) can
have two rows, distinguished by `part_label`. `is_main_faculty` marks the
principal teacher when two are assigned.
"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
    # Imported only for type checkers. Runtime uses string annotations + backref
    # so the faculty module never imports students.models at module load time.
    from app.modules.students.models import Batch, Division, Program


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class SubjectType(str, enum.Enum):
    THEORY = "theory"
    LAB = "lab"
    OTHER = "other"


# --------------------------------------------------------------------------- #
# Faculty
# --------------------------------------------------------------------------- #
class Faculty(TimestampMixin, Base):
    __tablename__ = "faculty"

    # Nullable: course books sometimes list a faculty member before KTU id is assigned.
    ktu_id: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Department = the program this faculty primarily belongs to. Nullable because
    # non-teaching or shared staff (maths, physics) may not map to one program.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="RESTRICT"),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # backref adds Program.faculty_members without editing students/models.py.
    department: Mapped["Program | None"] = relationship(backref="faculty_members")

    offerings: Mapped[list["CourseOffering"]] = relationship(
        back_populates="faculty"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Faculty {self.ktu_id or self.name}>"


# --------------------------------------------------------------------------- #
# Subject (course catalogue entry)
# --------------------------------------------------------------------------- #
class Subject(TimestampMixin, Base):
    """A course as defined in a scheme, independent of who teaches it or when."""

    __tablename__ = "subjects"

    code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    scheme: Mapped[str] = mapped_column(String(8), nullable=False)
    type: Mapped[SubjectType] = mapped_column(
        SAEnum(
            SubjectType,
            name="subject_type",
            native_enum=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=SubjectType.THEORY,
        server_default=SubjectType.THEORY.value,
    )

    __table_args__ = (
        # A code can recur across schemes with different credits/semester.
        UniqueConstraint("code", "scheme", name="uq_subjects_code_scheme"),
        CheckConstraint("semester BETWEEN 1 AND 8", name="semester_range"),
        Index("ix_subjects_scheme_semester", "scheme", "semester"),
    )

    offerings: Mapped[list["CourseOffering"]] = relationship(
        back_populates="subject"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Subject {self.code} scheme={self.scheme}>"


# --------------------------------------------------------------------------- #
# CourseOffering
# --------------------------------------------------------------------------- #
class CourseOffering(TimestampMixin, Base):
    """A teaching instance: (subject, faculty, batch, division, semester, year).

    Two rows for the same subject in the same batch/year are expected when the
    course is split into Part I and Part II with different faculty. `part_label`
    disambiguates; `is_main_faculty` identifies the primary teacher.
    """

    __tablename__ = "course_offerings"

    subject_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subjects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    faculty_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("faculty.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    division_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("divisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    program_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="RESTRICT"),
        nullable=False,
    )

    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    academic_year: Mapped[str] = mapped_column(String(8), nullable=False)  # "2022-23"
    slot: Mapped[str] = mapped_column(String(8), nullable=False)

    # e.g. "Part I", "Part II". Null when the course has a single faculty member.
    part_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_main_faculty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    __table_args__ = (
        CheckConstraint("semester BETWEEN 1 AND 8", name="semester_range"),
        # Primary report axis: same shape as on students, so program-wise joins
        # (offering -> students) hit an index on both sides.
        Index(
            "ix_course_offerings_batch_program_division",
            "batch_id",
            "program_id",
            "division_id",
        ),
        # "Course-wise faculty-wise performance": filter/group by subject within a
        # batch + semester.
        Index(
            "ix_course_offerings_subject_batch_semester",
            "subject_id",
            "batch_id",
            "semester",
        ),
        # "Faculty performance history": faculty -> batches across years.
        Index(
            "ix_course_offerings_faculty_batch_year",
            "faculty_id",
            "batch_id",
            "academic_year",
        ),
    )

    subject: Mapped[Subject] = relationship(back_populates="offerings")
    faculty: Mapped[Faculty] = relationship(back_populates="offerings")
    # backref auto-attaches CourseOffering to Program/Batch/Division without
    # modifying students/models.py.
    program: Mapped["Program"] = relationship(backref="course_offerings")
    batch: Mapped["Batch"] = relationship(backref="course_offerings")
    division: Mapped["Division | None"] = relationship(backref="course_offerings")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<CourseOffering subj={self.subject_id} fac={self.faculty_id} "
            f"ay={self.academic_year} sem={self.semester}>"
        )


__all__ = ["Faculty", "Subject", "SubjectType", "CourseOffering"]