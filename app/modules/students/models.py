# students/models
"""Programs, batches, divisions, and students.

Programs/batches/divisions live here because every other module (faculty,
results, uploads) references them via FKs. Keeping them co-located avoids
the circular-import dance that would otherwise occur if they were split out.
"""

from __future__ import annotations

import enum
import uuid

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


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class StudentStatus(str, enum.Enum):
    ACTIVE = "active"
    DROPPED = "dropped"
    GRADUATED = "graduated"
    LATERAL = "lateral"


# --------------------------------------------------------------------------- #
# Programs
# --------------------------------------------------------------------------- #
class Program(TimestampMixin, Base):
    __tablename__ = "programs"

    code: Mapped[str] = mapped_column(String(4), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    students: Mapped[list["Student"]] = relationship(back_populates="program")
    divisions: Mapped[list["Division"]] = relationship(back_populates="program")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Program {self.code}>"


# --------------------------------------------------------------------------- #
# Batches
# --------------------------------------------------------------------------- #
class Batch(TimestampMixin, Base):
    """A batch is shared across all programs (e.g. 2022-26 covers CS, ME, ...)."""

    __tablename__ = "batches"

    start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    end_year: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)

    __table_args__ = (
        CheckConstraint("end_year > start_year", name="end_after_start"),
    )

    students: Mapped[list["Student"]] = relationship(back_populates="batch")
    divisions: Mapped[list["Division"]] = relationship(back_populates="batch")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Batch {self.label}>"


# --------------------------------------------------------------------------- #
# Divisions
# --------------------------------------------------------------------------- #
class Division(TimestampMixin, Base):
    """Division like CS-2022-26-A. Scoped to a program + batch."""

    __tablename__ = "divisions"

    program_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # "default" is used for programs that do not split into divisions.
    name: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        UniqueConstraint("program_id", "batch_id", "name", name="uq_divisions_scope_name"),
        Index("ix_divisions_program_batch", "program_id", "batch_id"),
    )

    program: Mapped[Program] = relationship(back_populates="divisions")
    batch: Mapped[Batch] = relationship(back_populates="divisions")
    students: Mapped[list["Student"]] = relationship(back_populates="division")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Division program={self.program_id} batch={self.batch_id} name={self.name}>"


# --------------------------------------------------------------------------- #
# Students
# --------------------------------------------------------------------------- #
class Student(TimestampMixin, Base):
    __tablename__ = "students"

    register_no: Mapped[str] = mapped_column(
        String(16), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    program_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    division_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("divisions.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[StudentStatus] = mapped_column(
        SAEnum(
            StudentStatus,
            name="student_status",
            native_enum=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=StudentStatus.ACTIVE,
        server_default=StudentStatus.ACTIVE.value,
    )
    # True when the register number did not start with the expected college prefix.
    is_flagged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    __table_args__ = (
        # Primary report axis: batch -> program -> division.
        Index("ix_students_batch_program_division", "batch_id", "program_id", "division_id"),
    )

    program: Mapped[Program] = relationship(back_populates="students")
    batch: Mapped[Batch] = relationship(back_populates="students")
    division: Mapped[Division | None] = relationship(back_populates="students")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Student {self.register_no} status={self.status.value}>"


__all__ = [
    "Program",
    "Batch",
    "Division",
    "Student",
    "StudentStatus",
]