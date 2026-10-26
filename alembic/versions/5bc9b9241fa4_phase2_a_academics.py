"""phase2 a: academics"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "5bc9b9241fa4"
down_revision: str | None = "0001_create_users"
branch_labels = None
depends_on = None

student_status = postgresql.ENUM(
    "active", "dropped", "graduated", "lateral",
    name="student_status", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    student_status.create(bind, checkfirst=True)

    op.create_table(
        "programs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(4), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_programs_code", "programs", ["code"], unique=True)

    op.create_table(
        "batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("end_year", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("end_year > start_year", name="ck_batches_end_after_start"),
    )
    op.create_index("ix_batches_label", "batches", ["label"], unique=True)

    op.create_table(
        "divisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], name="fk_divisions_program_id_programs", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], name="fk_divisions_batch_id_batches", ondelete="RESTRICT"),
        sa.UniqueConstraint("program_id", "batch_id", "name", name="uq_divisions_scope_name"),
    )
    op.create_index("ix_divisions_program_batch", "divisions", ["program_id", "batch_id"])

    op.create_table(
        "students",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("register_no", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("division_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", student_status, nullable=False, server_default="active"),
        sa.Column("is_flagged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], name="fk_students_program_id_programs", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], name="fk_students_batch_id_batches", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["division_id"], ["divisions.id"], name="fk_students_division_id_divisions", ondelete="SET NULL"),
    )
    op.create_index("ix_students_register_no", "students", ["register_no"], unique=True)
    op.create_index("ix_students_program_id", "students", ["program_id"])
    op.create_index("ix_students_batch_id", "students", ["batch_id"])
    op.create_index("ix_students_batch_program_division", "students", ["batch_id", "program_id", "division_id"])


def downgrade() -> None:
    op.drop_table("students")
    op.drop_table("divisions")
    op.drop_table("batches")
    op.drop_table("programs")
    student_status.drop(op.get_bind(), checkfirst=True)
