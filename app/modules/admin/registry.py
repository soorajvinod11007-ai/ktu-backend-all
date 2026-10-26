"""Resource registry for the admin CRUD framework.

Every URL slug under ``/api/v1/admin`` maps to one of these configs.
Part 3 plugs dashboard / options / export / import on top; Part 4 supplies
the ``audit_writer`` used by every ``CrudService`` write.
"""

from __future__ import annotations

from app.common.crud import ResourceConfig
from app.modules.admin.resources.batches import CONFIG as _batches
from app.modules.admin.resources.course_offerings import CONFIG as _course_offerings
from app.modules.admin.resources.divisions import CONFIG as _divisions
from app.modules.admin.resources.exam_sessions import CONFIG as _exam_sessions
from app.modules.admin.resources.faculty import CONFIG as _faculty
from app.modules.admin.resources.grade_cards import CONFIG as _grade_cards
from app.modules.admin.resources.programs import CONFIG as _programs
from app.modules.admin.resources.result_history import CONFIG as _result_history
from app.modules.admin.resources.results import CONFIG as _results
from app.modules.admin.resources.students import CONFIG as _students
from app.modules.admin.resources.subjects import CONFIG as _subjects
from app.modules.admin.resources.upload_logs import CONFIG as _upload_logs
from app.modules.admin.resources.users import CONFIG as _users


RESOURCE_CONFIGS: list[ResourceConfig] = [
    _users,
    _programs,
    _batches,
    _divisions,
    _students,
    _faculty,
    _subjects,
    _course_offerings,
    _exam_sessions,
    _results,
    _grade_cards,
    _result_history,
    _upload_logs,
]


def get_config(name: str) -> ResourceConfig:
    for cfg in RESOURCE_CONFIGS:
        if cfg.name == name:
            return cfg
    raise KeyError(name)


__all__ = ["RESOURCE_CONFIGS", "get_config"]