from typing import Any

from app.common.crud import ResourceConfig
from app.modules.admin.schemas import (
    ExamSessionCreate,
    ExamSessionRead,
    ExamSessionUpdate,
)
from app.modules.results.models import ExamSession


def _row_mapper(e: ExamSession) -> dict[str, Any]:
    return {
        "id": e.id,
        "name": e.name,
        "exam_type": e.exam_type.value if hasattr(e.exam_type, "value") else e.exam_type,
        "created_at": e.created_at,
        "updated_at": e.updated_at,
        "deleted_at": e.deleted_at,
    }


CONFIG = ResourceConfig(
    name="exam-sessions",
    model=ExamSession,
    read_schema=ExamSessionRead,
    create_schema=ExamSessionCreate,
    update_schema=ExamSessionUpdate,
    search_fields=(ExamSession.name,),
    filter_fields={
        "exam_type": ExamSession.exam_type,
    },
    sortable_fields={
        "name": ExamSession.name,
        "created_at": ExamSession.created_at,
    },
    row_mapper=_row_mapper,
)
