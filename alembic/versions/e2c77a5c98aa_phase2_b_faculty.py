"""phase2 b: faculty"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e2c77a5c98aa"
down_revision: str | None = "5bc9b9241fa4"
branch_labels = None
depends_on = None

subject_type = postgresql.ENUM("theory", "lab", "other", name="subject_type", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    subject_type.create(bind, checkfirst=True)

    op.create_table(
        "faculty",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ktu_id", sa.String(32), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["department_id"], ["programs.id"], name="fk_faculty_department_id_programs", ondelete="RESTRICT"),
    )
    op.create_index("ix_faculty_ktu_id", "faculty", ["ktu_id"], unique=True)
    op.create_index("ix_faculty_name", "faculty", ["name"])

    op.create_table(
        "subjects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=True),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("scheme", sa.String(8), nullable=False),
        sa.Column("type", subject_type, nullable=False, server_default="theory"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("code", "scheme", name="uq_subjects_code_scheme"),
        sa.CheckConstraint("semester BETWEEN 1 AND 8", name="ck_subjects_semester_range"),
    )
    op.create_index("ix_subjects_code", "subjects", ["code"])
    op.create_index("ix_subjects_scheme_semester", "subjects", ["scheme", "semester"])

    op.create_table(
        "course_offerings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("faculty_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("division_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("academic_year", sa.String(8), nullable=False),
        sa.Column("slot", sa.String(8), nullable=False),
        sa.Column("part_label", sa.String(16), nullable=True),
        sa.Column("is_main_faculty", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], name="fk_course_offerings_subject_id_subjects", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["faculty_id"], ["faculty.id"], name="fk_course_offerings_faculty_id_faculty", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], name="fk_course_offerings_batch_id_batches", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["division_id"], ["divisions.id"], name="fk_course_offerings_division_id_divisions", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], name="fk_course_offerings_program_id_programs", ondelete="RESTRICT"),
        sa.CheckConstraint("semester BETWEEN 1 AND 8", name="ck_course_offerings_semester_range"),
    )
    op.create_index("ix_course_offerings_batch_program_division", "course_offerings", ["batch_id", "program_id", "division_id"])
    op.create_index("ix_course_offerings_subject_batch_semester", "course_offerings", ["subject_id", "batch_id", "semester"])
    op.create_index("ix_course_offerings_faculty_batch_year", "course_offerings", ["faculty_id", "batch_id", "academic_year"])


def downgrade() -> None:
    op.drop_table("course_offerings")
    op.drop_table("subjects")
    op.drop_table("faculty")
    subject_type.drop(op.get_bind(), checkfirst=True)
