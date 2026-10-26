"""Alembic environment. Reads DATABASE_URL from app settings and autodetects
every model imported via app.core.database.Base.metadata."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.core.database import Base


import app.models  # noqa: F401, E402  — registers every model on Base.metadata


# Import every model module so their tables register on Base.metadata.
# Add new lines here as modules are added in later phases.
from alembic.operations import Operations

_orig_create_fk = Operations.create_foreign_key


def _sqlite_safe_create_fk(self, constraint_name, source_table, referent_table, local_cols, remote_cols, **kw):
    bind = self.get_bind()
    if bind and bind.dialect.name == "sqlite":
        with self.batch_alter_table(source_table) as batch_op:
            batch_op.create_foreign_key(
                constraint_name, referent_table, local_cols, remote_cols, **kw
            )
    else:
        _orig_create_fk(self, constraint_name, source_table, referent_table, local_cols, remote_cols, **kw)


Operations.create_foreign_key = _sqlite_safe_create_fk

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the runtime URL.
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()