"""Parser for Master Student List Excel files."""

from __future__ import annotations

import io
import re
from typing import Any

import openpyxl

from app.common.register_no import parse_register_no
from app.modules.uploads.parsers.base import (
    BaseParser,
    ErrorCode,
    ParseError,
    ParseResult,
)

_REG_COL_PATTERNS = re.compile(
    r"reg(ister)?[\s_-]*(no|num|number)?|roll[\s_-]*(no)?", re.IGNORECASE
)
_NAME_COL_PATTERNS = re.compile(r"name|student[\s_-]*name|candidate[\s_-]*name", re.IGNORECASE)
_DIV_COL_PATTERNS = re.compile(r"div(ision)?|section", re.IGNORECASE)
_PROG_COL_PATTERNS = re.compile(r"prog(ram)?|branch|dept|department", re.IGNORECASE)


class StudentListParser(BaseParser):
    def parse(self, file_bytes: bytes, **kwargs: Any) -> ParseResult:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        except Exception as exc:
            return ParseResult(
                errors=[
                    ParseError(
                        page=1,
                        row=1,
                        code=ErrorCode.STRUCTURE_NOT_RECOGNISED,
                        message=f"Unable to read Excel workbook: {exc}",
                    )
                ]
            )

        rows: list[dict[str, Any]] = []
        errors: list[ParseError] = []
        seen_reg_nos: set[str] = set()

        for sheet_idx, sheet_name in enumerate(wb.sheetnames, start=1):
            ws = wb[sheet_name]
            iter_rows = ws.iter_rows(values_only=True)

            header_found = False
            reg_idx: int | None = None
            name_idx: int | None = None
            div_idx: int | None = None

            # Attempt to deduce division or program from sheet name (e.g. "CS-A", "CS_B", "ME")
            sheet_div: str | None = None
            sheet_clean = sheet_name.strip().upper()
            if (
                "A" in sheet_clean.split("-")
                or sheet_clean.endswith(" A")
                or sheet_clean.endswith("-A")
                or sheet_clean.endswith("_A")
            ):
                sheet_div = "A"
            elif (
                "B" in sheet_clean.split("-")
                or sheet_clean.endswith(" B")
                or sheet_clean.endswith("-B")
                or sheet_clean.endswith("_B")
            ):
                sheet_div = "B"

            row_num = 0
            for raw_row in iter_rows:
                row_num += 1
                if not raw_row or all(c is None or str(c).strip() == "" for c in raw_row):
                    continue

                cells = [str(c).strip() if c is not None else "" for c in raw_row]

                # Look for header row
                if not header_found:
                    for i, cell in enumerate(cells):
                        if _REG_COL_PATTERNS.fullmatch(cell) or cell.upper() in {
                            "REGISTER NO",
                            "REG NO",
                            "REG_NO",
                            "REGNO",
                        }:
                            reg_idx = i
                        elif _NAME_COL_PATTERNS.fullmatch(cell) or cell.upper() in {
                            "NAME",
                            "STUDENT NAME",
                        }:
                            name_idx = i
                        elif _DIV_COL_PATTERNS.fullmatch(cell) or cell.upper() in {
                            "DIV",
                            "DIVISION",
                            "SEC",
                            "SECTION",
                        }:
                            div_idx = i
                        elif _PROG_COL_PATTERNS.fullmatch(cell) or cell.upper() in {
                            "PROGRAM",
                            "BRANCH",
                        }:
                            pass

                    if reg_idx is not None and name_idx is not None:
                        header_found = True
                    continue

                # Data row
                reg_raw = cells[reg_idx] if reg_idx is not None and reg_idx < len(cells) else ""
                name_raw = cells[name_idx] if name_idx is not None and name_idx < len(cells) else ""
                div_raw = cells[div_idx] if div_idx is not None and div_idx < len(cells) else ""

                if not reg_raw:
                    continue

                reg_clean = re.sub(r"\s+", "", reg_raw).upper()
                name_clean = re.sub(r"\s+", " ", name_raw).strip()

                parsed = parse_register_no(reg_clean)
                if parsed is None:
                    errors.append(
                        ParseError(
                            page=sheet_idx,
                            row=row_num,
                            code=ErrorCode.STRUCTURE_NOT_RECOGNISED,
                            message=f"Invalid register number format: '{reg_raw}'",
                        )
                    )
                    continue

                if reg_clean in seen_reg_nos:
                    errors.append(
                        ParseError(
                            page=sheet_idx,
                            row=row_num,
                            code=ErrorCode.DUPLICATE_ROW,
                            message=f"Duplicate register number in file: '{reg_clean}'",
                        )
                    )
                    continue
                seen_reg_nos.add(reg_clean)

                # Division resolution
                div = (div_raw.strip().upper() if div_raw else None) or sheet_div
                if div in {"A", "DIV A", "DIVISION A"}:
                    div = "A"
                elif div in {"B", "DIV B", "DIVISION B"}:
                    div = "B"
                elif not div:
                    div = None

                # Special check for CS division
                if parsed.program_code == "CS" and not div:
                    errors.append(
                        ParseError(
                            page=sheet_idx,
                            row=row_num,
                            code=ErrorCode.MISSING_DIVISION,
                            message=(
                                f"Computer Science student '{reg_clean}' "
                                "requires division (A or B)"
                            ),
                        )
                    )

                is_flagged = not parsed.is_valid_prefix
                if is_flagged:
                    errors.append(
                        ParseError(
                            page=sheet_idx,
                            row=row_num,
                            code=ErrorCode.ODD_REGISTER_PREFIX,
                            message=(
                                f"Odd college prefix '{parsed.college_prefix}' for "
                                f"register number '{reg_clean}' (flagged)"
                            ),
                        )
                    )

                admission_year = parsed.admission_year
                batch_label = f"{admission_year}-{str(admission_year + 4)[-2:]}"

                rows.append(
                    {
                        "register_no": reg_clean,
                        "name": name_clean,
                        "program_code": parsed.program_code,
                        "admission_year": admission_year,
                        "batch_label": batch_label,
                        "division": div,
                        "is_flagged": is_flagged,
                        "status": "active",
                    }
                )

        return ParseResult(rows=rows, errors=errors, meta={"total_sheets": len(wb.sheetnames)})
