"""Unit tests for parse_register_no."""

import pytest

from app.modules.students.register_no import parse_register_no


class TestValidRegisters:
    def test_cs_standard(self) -> None:
        parsed = parse_register_no("NIE22CS045")
        assert parsed["program_code"] == "CS"
        assert parsed["admission_year"] == 2022
        assert parsed["batch_label"] == "2022-26"
        assert parsed["roll_number"] == 45
        assert parsed["is_odd_prefix"] is False

    def test_all_known_program_codes(self) -> None:
        for code in ("CS", "ME", "MC", "CE", "AD", "CC"):
            parsed = parse_register_no(f"NIE23{code}001")
            assert parsed["program_code"] == code
            assert parsed["batch_label"] == "2023-27"

    def test_odd_prefix_is_flagged_not_rejected(self) -> None:
        parsed = parse_register_no("SGI22CS013")
        assert parsed["program_code"] == "CS"
        assert parsed["is_odd_prefix"] is True

    def test_batch_label_rolls_century_correctly(self) -> None:
        # 2025-29: end year 2029 -> "2025-29"
        assert parse_register_no("NIE25CS001")["batch_label"] == "2025-29"

    def test_lowercase_is_normalised(self) -> None:
        parsed = parse_register_no("nie22cs045")
        assert parsed["program_code"] == "CS"
        assert parsed["admission_year"] == 2022

    def test_whitespace_is_stripped(self) -> None:
        parsed = parse_register_no("  NIE22CS045  ")
        assert parsed["roll_number"] == 45


class TestInvalidRegisters:
    @pytest.mark.parametrize(
        "value",
        [
            "",
            "NIE22C045",        # 1-letter program code
            "NIE22CS45",        # 2-digit roll
            "NIE22CS0045",      # 4-digit roll
            "NI22CS045",        # 2-letter prefix
            "NIE2CS045",        # 1-digit year
            "NIE22CSABC",       # non-numeric roll
            "NIE-22-CS-045",    # separators
            "not a register",
        ],
    )
    def test_rejects_malformed(self, value: str) -> None:
        with pytest.raises(ValueError):
            parse_register_no(value)

    def test_rejects_non_string(self) -> None:
        with pytest.raises(ValueError):
            parse_register_no(22045)  # type: ignore[arg-type]