"""KTU register-number parser.

Format: <college:3 letters><admission year:2 digits><program:2 letters><roll:3 digits>
Example: NIE22CS045 -> college=NIE, year=2022, program=CS, roll=45.

We do not enforce the NIE prefix — one SGI-prefixed student is known — we flag it
instead so it can be reviewed without blocking ingestion.
"""

from __future__ import annotations

import re
from typing import TypedDict

STANDARD_PREFIX = "NIE"
PROGRAM_DURATION_YEARS = 4

_REGISTER_NO_RE = re.compile(
    r"^(?P<prefix>[A-Z]{3})(?P<year>\d{2})(?P<program>[A-Z]{2})(?P<roll>\d{3})$"
)


class ParsedRegisterNo(TypedDict):
    program_code: str
    admission_year: int
    batch_label: str
    roll_number: int
    is_odd_prefix: bool


def parse_register_no(register_no: str) -> ParsedRegisterNo:
    """Split a KTU register number into its parts.

    Raises:
        ValueError: if the string does not match the expected shape.
    """
    if not isinstance(register_no, str):
        raise ValueError(f"register_no must be a string, got {type(register_no).__name__}")

    cleaned = register_no.strip().upper()
    match = _REGISTER_NO_RE.match(cleaned)
    if match is None:
        raise ValueError(f"Invalid register number format: {register_no!r}")

    admission_year = 2000 + int(match.group("year"))
    end_year = admission_year + PROGRAM_DURATION_YEARS
    # Batch label uses last two digits of the end year, e.g. 2022 -> "2022-26".
    batch_label = f"{admission_year}-{end_year % 100:02d}"

    return ParsedRegisterNo(
        program_code=match.group("program"),
        admission_year=admission_year,
        batch_label=batch_label,
        roll_number=int(match.group("roll")),
        is_odd_prefix=match.group("prefix") != STANDARD_PREFIX,
    )