"""phase2 d: uploads"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9bdefefc127f"
down_revision: str | None = "8e0ddbd36174"
branch_labels = None
depends_on = None

upload_file_type = postgresql.ENUM(
    "student_list", "course_book", "grade_card", "result", "revaluation",
    name="upload_file_type", create_type=False,
)
upload_status = postgresql.ENUM(
    "pending", "processing", "success", "partial", "failed",
    name="upload_status", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    upload_file_type.create(bind, checkfirst=True)
    upload_status.create(bind, checkfirst=True)

    op.create_table(
        "upload_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", upload_file_type, nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rows_parsed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", upload_status, nullable=False, server_default="pending"),
        sa.Column("error_summary", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], name="fk_upload_logs_uploaded_by_users", ondelete="RESTRICT"),
        sa.CheckConstraint("rows_parsed >= 0", name="ck_upload_logs_rows_parsed_non_negative"),
        sa.CheckConstraint("rows_failed >= 0", name="ck_upload_logs_rows_failed_non_negative"),
        sa.CheckConstraint("rows_failed <= rows_parsed", name="ck_upload_logs_rows_failed_le_parsed"),
    )
    op.create_index("ix_upload_logs_type_status_created", "upload_logs", ["file_type", "status", "created_at"])

    op.create_foreign_key(
        "fk_result_history_source_upload_id_upload_logs",
        source_table="result_history",
        referent_table="upload_logs",
        local_cols=["source_upload_id"],
        remote_cols=["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_result_history_source_upload_id_upload_logs", "result_history", type_="foreignkey")
    op.drop_table("upload_logs")
    bind = op.get_bind()
    upload_status.drop(bind, checkfirst=True)
    upload_file_type.drop(bind, checkfirst=True)
