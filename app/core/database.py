# core/database
"""SQLAlchemy 2.0 engine, session factory, declarative Base, and FastAPI dependency."""

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Constraint naming convention — makes Alembic autogenerate deterministic.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


is_sqlite = settings.DATABASE_URL.startswith("sqlite")
engine_kwargs: dict = {"future": True}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update(
        {
            "pool_pre_ping": True,
            "pool_size": 5,
            "max_overflow": 10,
            "pool_recycle": 1800,
        }
    )

engine = create_engine(
    settings.DATABASE_URL,
    **engine_kwargs,
)

if is_sqlite:
    from datetime import datetime, timezone
    from sqlalchemy import event
    import sqlalchemy as sa
    from sqlalchemy.dialects.sqlite.base import DATETIME

    class SQLiteDateTimeUTC(DATETIME):
        def result_processor(self, dialect, coltype):
            super_proc = super().result_processor(dialect, coltype)

            def process(value):
                res = super_proc(value) if super_proc else value
                if isinstance(res, datetime) and res.tzinfo is None:
                    return res.replace(tzinfo=timezone.utc)
                return res

            return process

    engine.dialect.colspecs[sa.DateTime] = SQLiteDateTimeUTC

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        try:
            dbapi_connection.create_function(
                "now", 0, lambda: datetime.now(timezone.utc).isoformat()
            )
        except Exception:
            pass

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """One session per request.

    Commits on clean exit, rolls back on any exception, always closes.
    Routers never call this directly — services receive the session
    from the router via a Depends chain.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()