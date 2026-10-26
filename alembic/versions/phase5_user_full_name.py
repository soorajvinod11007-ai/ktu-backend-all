"""phase 5a — add full_name to users table

Revision ID: phase5_user_full_name
Revises: phase4_admin_dashboard
Create Date: 2026-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "phase5_user_full_name"
down_revision = "phase4_admin_dashboard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind and bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(
                sa.Column("full_name", sa.String(255), nullable=True)
            )
    else:
        op.add_column(
            "users",
            sa.Column("full_name", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind and bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("full_name")
    else:
        op.drop_column("users", "full_name")
