"""Tests for parsers — C header, CSV, JSON, TOML."""

import json
import textwrap
from pathlib import Path

import pytest

from consync.models import Constant
from consync.parsers.c_header import parse_c_header
from consync.parsers.csv_parser import parse_csv
from consync.parsers.json_parser import parse_json


@pytest.fixture
def tmp_file(tmp_path):
    """Helper to create temp files with content."""
    def _create(filename: str, content: str) -> Path:
        p = tmp_path / filename
        p.write_text(textwrap.dedent(content))
        return p
    return _create


class TestCHeaderParser:
    def test_basic_const_double(self, tmp_file):
        f = tmp_file("test.h", """\
            #ifndef TEST_H
            #define TEST_H
            const double R_SENSE = 1.9999999999910001;  /* Ohm | Current sense resistor */
            const double R_PULLUP = 4706;  /* Ohm | I2C pull-up resistor */
            #endif
        """)
        result = parse_c_header(f)
        assert len(result) == 2
        assert result[0].name == "R_SENSE"
        assert result[0].value == 1.9999999999910001
        assert result[0].unit == "Ohm"
        assert result[0].description == "Current sense resistor"
        assert result[1].name == "R_PULLUP"
        assert result[1].value == 4706

    def test_scientific_notation(self, tmp_file):
        f = tmp_file("sci.h", """\
            const double C_FILTER = 4.7832940e-07;  /* F | Input filter */
        """)
        result = parse_c_header(f)
        assert len(result) == 1
        assert abs(result[0].value - 4.7832940e-07) < 1e-20

    def test_no_comment(self, tmp_file):
        f = tmp_file("nocomm.h", """\
            const double PI = 3.14159265358979;
        """)
        result = parse_c_header(f)
        assert len(result) == 1
        assert result[0].unit == ""
        assert result[0].description == ""

    def test_static_const(self, tmp_file):
        f = tmp_file("static.h", """\
            static const double GAIN = 10.5;  /* V/V | Amplifier gain */
        """)
        result = parse_c_header(f)
        assert len(result) == 1
        assert result[0].name == "GAIN"

    def test_define_macro(self, tmp_file):
        f = tmp_file("define.h", """\
            #define MAX_VOLTAGE 5.0  /* V | Maximum input */
        """)
        result = parse_c_header(f)
        assert len(result) == 1
        assert result[0].name == "MAX_VOLTAGE"
        assert result[0].value == 5.0

    def test_hex_define(self, tmp_file):
        f = tmp_file("hex.h", """\
            #define REG_ADDR 0xFF
        """)
        result = parse_c_header(f)
        assert len(result) == 1
        assert result[0].value == 255

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_c_header("/nonexistent/file.h")


class TestCSVParser:
    def test_basic_csv(self, tmp_file):
        f = tmp_file("test.csv", """\
            Name,Value,Unit,Description
            R_SENSE,1.999,Ohm,Current sense
            R_PULLUP,4706,Ohm,Pull-up
        """)
        result = parse_csv(f)
        assert len(result) == 2
        assert result[0].name == "R_SENSE"
        assert result[0].value == 1.999
        assert result[1].value == 4706

    def test_tab_separated(self, tmp_file):
        f = tmp_file("test.tsv", "Name\tValue\nPI\t3.14\n")
        result = parse_csv(f, delimiter="\t")
        assert len(result) == 1
        assert result[0].name == "PI"

    def test_semicolons(self, tmp_file):
        f = tmp_file("test.csv", "Name;Value\nPI;3.14\n")
        result = parse_csv(f, delimiter=";")
        assert len(result) == 1

    def test_empty_rows_skipped(self, tmp_file):
        f = tmp_file("test.csv", "Name,Value\nPI,3.14\n\n,,\nE,2.718\n")
        result = parse_csv(f)
        assert len(result) == 2


class TestJSONParser:
    def test_flat_format(self, tmp_file):
        f = tmp_file("flat.json", json.dumps({"R_SENSE": 1.999, "R_PULLUP": 4706}))
        result = parse_json(f)
        assert len(result) == 2
        assert result[0].value == 1.999 or result[1].value == 1.999

    def test_array_format(self, tmp_file):
        data = [
            {"name": "R_SENSE", "value": 1.999, "unit": "Ohm", "description": "Sense resistor"},
            {"name": "R_PULLUP", "value": 4706, "unit": "Ohm"},
        ]
        f = tmp_file("array.json", json.dumps(data))
        result = parse_json(f)
        assert len(result) == 2
        assert result[0].unit == "Ohm"

    def test_nested_format(self, tmp_file):
        data = {
            "R_SENSE": {"value": 1.999, "unit": "Ohm", "description": "Sense"},
            "R_PULLUP": {"value": 4706},
        }
        f = tmp_file("nested.json", json.dumps(data))
        result = parse_json(f)
        assert len(result) == 2

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_json("/nonexistent.json")
