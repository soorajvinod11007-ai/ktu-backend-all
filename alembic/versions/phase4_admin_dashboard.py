"""phase 4 — audit_logs, upload_logs columns, result_change_type.manual_edit, perf indexes

Revision ID: phase4_admin_dashboard
Revises: <PUT YOUR PHASE 3 HEAD HERE>
Create Date: 2026-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "phase4_admin_dashboard"
down_revision = "0cff613a0b97"  # <-- set this to the current head (e.g. "phase3_abc123")
branch_labels = None
depends_on = None


# Filter / sort columns that were not indexed during Phases 1–3.
# CREATE INDEX IF NOT EXISTS keeps re-runs safe; indexes added by the
# model layer (ix_*) are skipped automatically.
_PERF_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_programs_name ON programs (name)",
    "CREATE INDEX IF NOT EXISTS ix_batches_start_year ON batches (start_year)",
    "CREATE INDEX IF NOT EXISTS ix_batches_end_year ON batches (end_year)",
    "CREATE INDEX IF NOT EXISTS ix_students_name ON students (name)",
    "CREATE INDEX IF NOT EXISTS ix_students_status ON students (status)",
    "CREATE INDEX IF NOT EXISTS ix_students_is_flagged ON students (is_flagged)",
    "CREATE INDEX IF NOT EXISTS ix_faculty_is_active ON faculty (is_active)",
    "CREATE INDEX IF NOT EXISTS ix_subjects_name ON subjects (name)",
    "CREATE INDEX IF NOT EXISTS ix_subjects_semester ON subjects (semester)",
    "CREATE INDEX IF NOT EXISTS ix_subjects_scheme ON subjects (scheme)",
    "CREATE INDEX IF NOT EXISTS ix_course_offerings_program_id ON course_offerings (program_id)",
    "CREATE INDEX IF NOT EXISTS ix_course_offerings_batch_id ON course_offerings (batch_id)",
    "CREATE INDEX IF NOT EXISTS ix_course_offerings_division_id ON course_offerings (division_id)",
    "CREATE INDEX IF NOT EXISTS ix_course_offerings_subject_id ON course_offerings (subject_id)",
    "CREATE INDEX IF NOT EXISTS ix_course_offerings_faculty_id ON course_offerings (faculty_id)",
    "CREATE INDEX IF NOT EXISTS ix_course_offerings_semester ON course_offerings (semester)",
    "CREATE INDEX IF NOT EXISTS ix_course_offerings_academic_year ON course_offerings (academic_year)",
    "CREATE INDEX IF NOT EXISTS ix_exam_sessions_exam_type ON exam_sessions (exam_type)",
    "CREATE INDEX IF NOT EXISTS ix_semester_results_student_id ON semester_results (student_id)",
    "CREATE INDEX IF NOT EXISTS ix_semester_results_subject_id ON semester_results (subject_id)",
    "CREATE INDEX IF NOT EXISTS ix_semester_results_exam_session_id ON semester_results (exam_session_id)",
    "CREATE INDEX IF NOT EXISTS ix_semester_results_semester ON semester_results (semester)",
    "CREATE INDEX IF NOT EXISTS ix_semester_results_status ON semester_results (status)",
    "CREATE INDEX IF NOT EXISTS ix_grade_cards_student_id ON grade_cards (student_id)",
    "CREATE INDEX IF NOT EXISTS ix_grade_cards_semester ON grade_cards (semester)",
    "CREATE INDEX IF NOT EXISTS ix_grade_cards_exam_session_id ON grade_cards (exam_session_id)",
    "CREATE INDEX IF NOT EXISTS ix_result_history_semester_result_id ON result_history (semester_result_id)",
    "CREATE INDEX IF NOT EXISTS ix_upload_logs_file_type ON upload_logs (file_type)",
    "CREATE INDEX IF NOT EXISTS ix_upload_logs_status ON upload_logs (status)",
]


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind and bind.dialect.name == "sqlite"

    # 1. Extend the existing result_change_type enum.
    if not is_sqlite:
        op.execute(
            "ALTER TYPE change_type ADD VALUE IF NOT EXISTS 'manual_edit'"
        )

    # 2. audit_action enum + audit_logs table.
    if not is_sqlite:
        audit_action = postgresql.ENUM(
            "create",
            "update",
            "delete",
            "restore",
            "import",
            "export",
            name="audit_action",
            create_type=False,
        )
        op.execute(
            "DO $$ BEGIN "
            "CREATE TYPE audit_action AS ENUM "
            "('create','update','delete','restore','import','export'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
    else:
        audit_action = sa.String(32)

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", audit_action, nullable=False),
        sa.Column("resource", sa.String(64), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource", "audit_logs", ["resource"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index(
        "ix_audit_logs_resource_created_at",
        "audit_logs",
        ["resource", "created_at"],
    )

    # 3. upload_logs: two new columns used by the import preview flow.
    if is_sqlite:
        with op.batch_alter_table("upload_logs") as batch_op:
            batch_op.add_column(sa.Column("resource", sa.String(64), nullable=True))
            batch_op.add_column(sa.Column("preview_payload", sa.JSON(), nullable=True))
            batch_op.create_index("ix_upload_logs_resource", ["resource"])
    else:
        op.add_column(
            "upload_logs", sa.Column("resource", sa.String(64), nullable=True)
        )
        op.add_column(
            "upload_logs",
            sa.Column("preview_payload", postgresql.JSONB, nullable=True),
        )
        op.create_index("ix_upload_logs_resource", "upload_logs", ["resource"])

    # 4. Performance indexes for admin filter/sort fields.
    for sql in _PERF_INDEX_SQL:
        bind.execute(sa.text(sql))


def downgrade() -> None:
    bind = op.get_bind()
    for sql in _PERF_INDEX_SQL:
        name = sql.split("ix_", 1)[1].split(" ", 1)[0]
        bind.execute(sa.text(f"DROP INDEX IF EXISTS ix_{name}"))

    op.drop_index("ix_upload_logs_resource", table_name="upload_logs")
    op.drop_column("upload_logs", "preview_payload")
    op.drop_column("upload_logs", "resource")

    op.drop_table("audit_logs")
    op.execute("DROP TYPE IF EXISTS audit_action")

    # Note: Postgres cannot remove a value from an existing enum without
    # dropping/recreating the type. Leaving 'manual_edit' in place on
    # downgrade is the safe, non-destructive choice.