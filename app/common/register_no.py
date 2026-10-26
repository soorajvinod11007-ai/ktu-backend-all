"""Parse KTU-style register numbers used at Nirmala College of Engineering.

Format: <college_prefix><2-digit-year><2-letter-program-code><3-digit-roll>
Example: NIE22CS045  =  college=NIE, year=22, program_code=CS, roll=045

Known college prefix: NIE (main). Other prefixes (e.g. SGI) exist and should be
flagged but NOT rejected (is_flagged = True, still imported).

Valid program codes (Phase 1 data): CS, ME, MC, CE, AD, CC
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MAIN_PREFIX = "NIE"
_KNOWN_CODES = frozenset({"CS", "ME", "MC", "CE", "AD", "CC"})
_PATTERN = re.compile(
    r"^(?P<college>[A-Z]{1,5})(?P<year>\d{2})(?P<code>[A-Z]{2})(?P<roll>\d{3})$"
)


@dataclass(frozen=True)
class ParsedRegisterNo:
    raw: str
    college_prefix: str
    admission_year: int
    program_code: str
    roll: str
    is_valid_prefix: bool


def parse_register_no(register_no: str):
    if not register_no:
        return None
    m = _PATTERN.match(register_no.strip().upper())
    if m is None:
        return None

    college = m.group("college")
    year_2 = int(m.group("year"))
    code = m.group("code")
    roll = m.group("roll")
    full_year = 2000 + year_2

    return ParsedRegisterNo(
        raw=register_no,
        college_prefix=college,
        admission_year=full_year,
        program_code=code,
        roll=roll,
        is_valid_prefix=(college == _MAIN_PREFIX and code in _KNOWN_CODES),
    )


__all__ = ["parse_register_no", "ParsedRegisterNo"]
