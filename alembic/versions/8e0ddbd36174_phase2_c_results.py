"""phase2 c: results"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8e0ddbd36174"
down_revision: str | None = "e2c77a5c98aa"
branch_labels = None
depends_on = None

exam_type = postgresql.ENUM("regular", "supplementary", name="exam_type", create_type=False)
grade = postgresql.ENUM(
    "S", "A+", "A", "B+", "B", "C+", "C", "D", "P", "F", "FE", "AB", "Withheld", "TBP",
    name="grade", create_type=False,
)
result_status = postgresql.ENUM("pass", "fail", "absent", "withheld", "tbp", name="result_status", create_type=False)
change_type = postgresql.ENUM("revaluation", "supply", name="change_type", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (exam_type, grade, result_status, change_type):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "exam_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("exam_type", exam_type, nullable=False, server_default="regular"),
        sa.Column("scheme", sa.String(8), nullable=False),
        sa.Column("published_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name", name="uq_exam_sessions_name"),
    )
    op.create_index("ix_exam_sessions_type_published", "exam_sessions", ["exam_type", "published_on"])

    op.create_table(
        "semester_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exam_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("grade", grade, nullable=True),
        sa.Column("status", result_status, nullable=False),
        sa.Column("is_regular_attempt", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], name="fk_semester_results_student_id_students", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], name="fk_semester_results_subject_id_subjects", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["exam_session_id"], ["exam_sessions.id"], name="fk_semester_results_exam_session_id_exam_sessions", ondelete="RESTRICT"),
        sa.UniqueConstraint("student_id", "subject_id", "exam_session_id", name="uq_semester_results_natural_key"),
        sa.CheckConstraint("semester BETWEEN 1 AND 8", name="ck_semester_results_semester_range"),
    )
    op.create_index("ix_semester_results_student_id", "semester_results", ["student_id"])
    op.create_index("ix_semester_results_subject_session", "semester_results", ["subject_id", "exam_session_id"])
    op.create_index("ix_semester_results_semester_status", "semester_results", ["semester", "status"])

    op.create_table(
        "result_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("semester_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_grade", grade, nullable=True),
        sa.Column("new_grade", grade, nullable=True),
        sa.Column("old_status", result_status, nullable=True),
        sa.Column("new_status", result_status, nullable=True),
        sa.Column("change_type", change_type, nullable=False),
        sa.Column("source_upload_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["semester_result_id"], ["semester_results.id"], name="fk_result_history_semester_result_id_semester_results", ondelete="RESTRICT"),
    )
    op.create_index("ix_result_history_semester_result_id", "result_history", ["semester_result_id"])

    op.create_table(
        "grade_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("exam_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("earned_credits", sa.Integer(), nullable=True),
        sa.Column("cumulative_credits", sa.Integer(), nullable=True),
        sa.Column("sgpa", sa.Float(), nullable=True),
        sa.Column("cgpa", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], name="fk_grade_cards_student_id_students", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["exam_session_id"], ["exam_sessions.id"], name="fk_grade_cards_exam_session_id_exam_sessions", ondelete="RESTRICT"),
        sa.UniqueConstraint("student_id", "semester", "exam_session_id", name="uq_grade_cards_natural_key"),
        sa.CheckConstraint("semester BETWEEN 1 AND 8", name="ck_grade_cards_semester_range"),
        sa.CheckConstraint("sgpa IS NULL OR (sgpa >= 0 AND sgpa <= 10)", name="ck_grade_cards_sgpa_range"),
        sa.CheckConstraint("cgpa IS NULL OR (cgpa >= 0 AND cgpa <= 10)", name="ck_grade_cards_cgpa_range"),
        sa.CheckConstraint("earned_credits IS NULL OR earned_credits >= 0", name="ck_grade_cards_earned_credits_non_negative"),
        sa.CheckConstraint("cumulative_credits IS NULL OR cumulative_credits >= 0", name="ck_grade_cards_cumulative_credits_non_negative"),
    )
    op.create_index("ix_grade_cards_student_id", "grade_cards", ["student_id"])


def downgrade() -> None:
    op.drop_table("grade_cards")
    op.drop_table("result_history")
    op.drop_table("semester_results")
    op.drop_table("exam_sessions")
    bind = op.get_bind()
    for enum in (change_type, result_status, grade, exam_type):
        enum.drop(bind, checkfirst=True)
