"""phase 5 — upload_logs columns (file_hash, stored_path, exam_session_id) + upload_status enum values

Revision ID: phase5_uploads
Revises: phase5_user_full_name
Create Date: 2026-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "phase5_uploads"
down_revision = "phase5_user_full_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind and bind.dialect.name == "sqlite"

    if not is_sqlite:
        # Extend Postgres upload_status enum with new statuses
        for val in ("preview", "confirmed", "completed", "cancelled", "committed"):
            op.execute(
                f"ALTER TYPE upload_status ADD VALUE IF NOT EXISTS '{val}'"
            )

    if is_sqlite:
        with op.batch_alter_table("upload_logs") as batch_op:
            batch_op.add_column(sa.Column("file_hash", sa.String(64), nullable=True))
            batch_op.add_column(sa.Column("stored_path", sa.String(512), nullable=True))
            batch_op.add_column(
                sa.Column(
                    "exam_session_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                )
            )
            batch_op.create_index("ix_upload_logs_file_hash", ["file_hash"])
    else:
        op.add_column(
            "upload_logs", sa.Column("file_hash", sa.String(64), nullable=True)
        )
        op.add_column(
            "upload_logs", sa.Column("stored_path", sa.String(512), nullable=True)
        )
        op.add_column(
            "upload_logs",
            sa.Column(
                "exam_session_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("exam_sessions.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index("ix_upload_logs_file_hash", "upload_logs", ["file_hash"])


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind and bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("upload_logs") as batch_op:
            batch_op.drop_index("ix_upload_logs_file_hash")
            batch_op.drop_column("exam_session_id")
            batch_op.drop_column("stored_path")
            batch_op.drop_column("file_hash")
    else:
        op.drop_index("ix_upload_logs_file_hash", table_name="upload_logs")
        op.drop_column("upload_logs", "exam_session_id")
        op.drop_column("upload_logs", "stored_path")
        op.drop_column("upload_logs", "file_hash")
