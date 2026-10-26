"""Parser for KTU Revaluation Result PDFs."""

from __future__ import annotations

from typing import Any

from app.modules.uploads.parsers.base import ParseResult
from app.modules.uploads.parsers.result_pdf import ResultPdfParser


class RevaluationPdfParser(ResultPdfParser):
    def parse(self, file_bytes: bytes, **kwargs: Any) -> ParseResult:
        result = super().parse(file_bytes, **kwargs)
        # Mark revaluation flag on metadata and rows
        result.meta["is_revaluation"] = True
        for row in result.rows:
            row["is_revaluation"] = True
            row["is_no_change"] = row.get("status") == "no_change"
        return result
