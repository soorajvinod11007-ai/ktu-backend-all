"""Seed the first admin user plus Phase 2 academic reference data.

Reads ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD from the environment.
Idempotent — re-running is safe.

Set SEED_SKIP_ADMIN=1 to seed only academic data (useful in CI where a real
admin password should not be baked into the environment).
"""

from __future__ import annotations

import logging
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.modules.auth.models import User, UserRole
from app.modules.students.models import Batch, Division, Program

logger = logging.getLogger("scripts.seed")


# --------------------------------------------------------------------------- #
# Config — edit these and re-run.
# --------------------------------------------------------------------------- #
PROGRAMS: list[dict[str, str]] = [
    {"code": "CS", "name": "Computer Science and Engineering"},
    {"code": "ME", "name": "Mechanical Engineering"},
    {"code": "MC", "name": "Mechatronics Engineering"},
    {"code": "CE", "name": "Civil Engineering"},
    {"code": "AD", "name": "Artificial Intelligence and Data Science"},
    {"code": "CC", "name": "Cyber Security"},
]

BATCHES: list[tuple[int, int]] = [
    (2019, 2023),
    (2020, 2024),
    (2021, 2025),
    (2022, 2026),
    (2023, 2027),
    (2024, 2028),
    (2025, 2029),
]

# CS only, for now. Add more program codes here as new splits arrive.
DIVISION_CONFIG: dict[str, dict[str, object]] = {
    "CS": {
        "batch_labels": ["2022-26", "2023-27", "2024-28", "2025-29"],
        "names": ["A", "B"],
    },
}


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
def seed_admin() -> None:
    if os.environ.get("SEED_SKIP_ADMIN") == "1":
        logger.info("admin seed skipped (SEED_SKIP_ADMIN=1)")
        return

    username = os.environ.get("ADMIN_USERNAME", "admin")
    email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
    password = os.environ.get("ADMIN_PASSWORD")

    if not password:
        logger.warning(
            "ADMIN_PASSWORD not set — skipping admin seed, continuing with academics"
        )
        return

    db = SessionLocal()
    try:
        existing = db.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("admin already exists, skipping", extra={"username": username})
            return
        db.add(
            User(
                username=username,
                email=email,
                hashed_password=hash_password(password),
                role=UserRole.ADMIN,
                is_active=True,
            )
        )
        db.commit()
        logger.info("admin created", extra={"username": username})
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Academic reference data
# --------------------------------------------------------------------------- #
def _batch_label(start_year: int, end_year: int) -> str:
    return f"{start_year}-{end_year % 100:02d}"


def _upsert_program(db: Session, *, code: str, name: str) -> Program:
    obj = db.execute(select(Program).where(Program.code == code)).scalar_one_or_none()
    if obj is None:
        obj = Program(code=code, name=name)
        db.add(obj)
        db.flush()
        logger.info("program created", extra={"code": code})
    elif obj.name != name:
        obj.name = name
        db.flush()
        logger.info("program renamed", extra={"code": code, "program_name": name})
    else:
        logger.info("program exists, skipping", extra={"code": code})
    return obj


def _upsert_batch(db: Session, *, start_year: int, end_year: int) -> Batch:
    label = _batch_label(start_year, end_year)
    obj = db.execute(select(Batch).where(Batch.label == label)).scalar_one_or_none()
    if obj is None:
        obj = Batch(start_year=start_year, end_year=end_year, label=label)
        db.add(obj)
        db.flush()
        logger.info("batch created", extra={"label": label})
    else:
        logger.info("batch exists, skipping", extra={"label": label})
    return obj


def _upsert_division(
    db: Session, *, program_id, batch_id, name: str
) -> Division:
    obj = db.execute(
        select(Division).where(
            Division.program_id == program_id,
            Division.batch_id == batch_id,
            Division.name == name,
        )
    ).scalar_one_or_none()
    if obj is None:
        obj = Division(program_id=program_id, batch_id=batch_id, name=name)
        db.add(obj)
        db.flush()
        logger.info("division created", extra={"division_name": name})
    else:
        logger.info("division exists, skipping", extra={"division_name": name})
    return obj


def seed_academics() -> None:
    db = SessionLocal()
    try:
        programs_by_code: dict[str, Program] = {}
        for spec in PROGRAMS:
            programs_by_code[spec["code"]] = _upsert_program(
                db, code=spec["code"], name=spec["name"]
            )

        batches_by_label: dict[str, Batch] = {}
        for start, end in BATCHES:
            label = _batch_label(start, end)
            batches_by_label[label] = _upsert_batch(
                db, start_year=start, end_year=end
            )

        for program_code, cfg in DIVISION_CONFIG.items():
            program = programs_by_code.get(program_code)
            if program is None:
                logger.warning(
                    "division config references unknown program",
                    extra={"program_code": program_code},
                )
                continue
            for label in cfg["batch_labels"]:  # type: ignore[union-attr]
                batch = batches_by_label.get(label)
                if batch is None:
                    logger.warning(
                        "division config references unknown batch",
                        extra={"program_code": program_code, "batch_label": label},
                    )
                    continue
                for div_name in cfg["names"]:  # type: ignore[union-attr]
                    _upsert_division(
                        db,
                        program_id=program.id,
                        batch_id=batch.id,
                        name=div_name,
                    )

        db.commit()
        logger.info("academic seed complete")
    except Exception:
        db.rollback()
        logger.exception("academic seed failed")
        raise
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #
def main() -> None:
    configure_logging()
    seed_admin()
    seed_academics()


if __name__ == "__main__":
    main()