"""Tests for precision formatting module."""

import math

from consync.precision import (
    format_float,
    format_c_double,
    format_scientific,
    format_fixed,
    parse_number,
    significant_digits,
)


class TestFormatFloat:
    def test_integer_value(self):
        assert format_float(4700.0, 17) == "4700"

    def test_high_precision_decimal(self):
        result = format_float(1.20029384729384, 17)
        # Should round-trip
        assert float(result) == 1.20029384729384

    def test_scientific_notation_small(self):
        result = format_float(4.7832940e-07, 17)
        assert float(result) == 4.7832940e-07

    def test_large_number(self):
        result = format_float(299872.93847293, 17)
        assert float(result) == 299872.93847293

    def test_negative(self):
        result = format_float(-3.14159, 17)
        assert float(result) == -3.14159

    def test_zero(self):
        assert format_float(0.0, 17) == "0"

    def test_nan(self):
        assert format_float(float("nan"), 17) == "NAN"

    def test_inf(self):
        assert format_float(float("inf"), 17) == "INF"
        assert format_float(float("-inf"), 17) == "-INF"

    def test_low_precision(self):
        result = format_float(3.14159265358979, 4)
        assert result == "3.142"

    def test_precision_clamp_min(self):
        # precision < 1 should be clamped to 1
        result = format_float(3.14, 0)
        assert float(result) != 0  # should still produce something

    def test_round_trip_17_digits(self):
        """17 significant digits guarantees IEEE 754 round-trip."""
        values = [
            1.9999999999910001,
            4.7832939999999996e-07,
            1.00293e-09,
            100029.4829183,
            0.00039284729384,
        ]
        for v in values:
            formatted = format_float(v, 17)
            assert float(formatted) == v, f"Round-trip failed for {v}: got {float(formatted)}"


class TestFormatCDouble:
    def test_same_as_format_float(self):
        assert format_c_double(3.14, 17) == format_float(3.14, 17)


class TestFormatScientific:
    def test_large_number(self):
        result = format_scientific(4700.0, 2)
        assert "e" in result.lower()
        assert float(result) == 4700.0

    def test_small_number(self):
        result = format_scientific(4.7832940e-07, 7)
        assert "e" in result.lower()


class TestFormatFixed:
    def test_decimal_places(self):
        result = format_fixed(1.20029384729384, 14)
        assert "1.2002938472938" in result

    def test_no_trailing_zeros(self):
        result = format_fixed(1.5, 10)
        assert not result.endswith("0")


class TestParseNumber:
    def test_integer(self):
        assert parse_number("4700") == 4700
        assert isinstance(parse_number("4700"), int)

    def test_float(self):
        assert parse_number("3.14") == 3.14
        assert isinstance(parse_number("3.14"), float)

    def test_scientific(self):
        assert parse_number("4.7e-07") == 4.7e-07

    def test_hex(self):
        assert parse_number("0xFF") == 255
        assert isinstance(parse_number("0xFF"), int)

    def test_binary(self):
        assert parse_number("0b1010") == 10

    def test_underscores(self):
        assert parse_number("1_000_000") == 1000000

    def test_whitespace(self):
        assert parse_number("  42  ") == 42


class TestSignificantDigits:
    def test_integer(self):
        assert significant_digits(4700.0) >= 2

    def test_high_precision(self):
        assert significant_digits(1.20029384729384) >= 14

    def test_zero(self):
        assert significant_digits(0.0) == 1
