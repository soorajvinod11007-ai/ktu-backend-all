"""Aggregate import so Alembic's env.py only imports one module.

Every model module must be imported here, otherwise autogenerate silently
misses tables and `sorted_tables()` raises NoReferencedTableError when a FK
points at an unregistered table.
"""

# Phase 1
from app.modules.auth.models import User  # noqa: F401

# Phase 2 — Part 1
from app.modules.students.models import (  # noqa: F401
    Batch, Division, Program, Student,
)

# Phase 2 — Part 2
from app.modules.faculty.models import (  # noqa: F401
    CourseOffering, Faculty, Subject,
)

# Phase 2 — Part 3
from app.modules.results.models import (  # noqa: F401
    ExamSession, GradeCard, ResultHistory, SemesterResult,
)

# Phase 2 — Part 4
from app.modules.uploads.models import UploadLog  # noqa: F401
