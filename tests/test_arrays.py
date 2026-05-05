"""Tests for array constant support across parsers and renderers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from consync.models import Constant, ConstantType, MappingConfig


# ═══════════════════════════════════════════════════════════════════════════════
# Model tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestConstantArrayModel:
    """Test the Constant model with array values."""

    def test_int_array_type(self):
        c = Constant(name="THRESHOLDS", value=[50, 100, 150, 200])
        assert c.type == ConstantType.ARRAY_INT
        assert c.is_array
        assert c.is_numeric

    def test_float_array_type(self):
        c = Constant(name="GAINS", value=[1.0, 2.5, 3.7])
        assert c.type == ConstantType.ARRAY_FLOAT
        assert c.is_array
        assert c.is_numeric

    def test_string_array_type(self):
        c = Constant(name="LABELS", value=["low", "med", "high"])
        assert c.type == ConstantType.ARRAY_STRING
        assert c.is_array
        assert not c.is_numeric

    def test_empty_array_defaults_to_int(self):
        c = Constant(name="EMPTY", value=[])
        assert c.type == ConstantType.ARRAY_INT
        assert c.is_array

    def test_scalar_not_array(self):
        c = Constant(name="X", value=42)
        assert not c.is_array
        assert c.type == ConstantType.INT


# ═══════════════════════════════════════════════════════════════════════════════
# CSV parser tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCSVArrayParsing:
    """Test CSV parser recognizes pipe-delimited arrays."""

    def test_int_array_pipe(self, tmp_path):
        csv_file = tmp_path / "params.csv"
        csv_file.write_text(
            "name,value,unit,description\n"
            "THRESHOLDS,50|100|150|200|250,bar,Pressure thresholds\n"
            "SCALAR,42,,A normal int\n"
        )
        from consync.parsers.csv_parser import parse_csv
        result = parse_csv(csv_file)

        assert len(result) == 2
        assert result[0].name == "THRESHOLDS"
        assert result[0].value == [50, 100, 150, 200, 250]
        assert result[0].unit == "bar"
        assert result[1].name == "SCALAR"
        assert result[1].value == 42

    def test_float_array_pipe(self, tmp_path):
        csv_file = tmp_path / "gains.csv"
        csv_file.write_text(
            "name,value,unit,description\n"
            "PID_GAINS,1.5|2.7|0.3,,PID controller gains\n"
        )
        from consync.parsers.csv_parser import parse_csv
        result = parse_csv(csv_file)

        assert result[0].value == [1.5, 2.7, 0.3]
        assert result[0].type == ConstantType.ARRAY_FLOAT

    def test_hex_array_pipe(self, tmp_path):
        csv_file = tmp_path / "ids.csv"
        csv_file.write_text(
            "name,value,unit,description\n"
            "CAN_IDS,0x1A3|0x2B4|0x3C5,,CAN message IDs\n"
        )
        from consync.parsers.csv_parser import parse_csv
        result = parse_csv(csv_file)

        assert result[0].value == [0x1A3, 0x2B4, 0x3C5]
        assert result[0].type == ConstantType.ARRAY_INT

    def test_string_array_semicolon(self, tmp_path):
        csv_file = tmp_path / "labels.csv"
        csv_file.write_text(
            "name,value,unit,description\n"
            "STATES,IDLE;RUNNING;ERROR,,FSM states\n"
        )
        from consync.parsers.csv_parser import parse_csv
        result = parse_csv(csv_file)

        assert result[0].value == ["IDLE", "RUNNING", "ERROR"]
        assert result[0].type == ConstantType.ARRAY_STRING


# ═══════════════════════════════════════════════════════════════════════════════
# JSON parser tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestJSONArrayParsing:
    """Test JSON parser with native array values."""

    def test_flat_format_with_array(self, tmp_path):
        json_file = tmp_path / "params.json"
        json_file.write_text(json.dumps({
            "SCALAR": 42,
            "THRESHOLDS": [50, 100, 150, 200, 250],
            "GAINS": [1.5, 2.7, 0.3],
        }))
        from consync.parsers.json_parser import parse_json
        result = parse_json(json_file)

        by_name = {c.name: c for c in result}
        assert by_name["SCALAR"].value == 42
        assert by_name["THRESHOLDS"].value == [50, 100, 150, 200, 250]
        assert by_name["GAINS"].value == [1.5, 2.7, 0.3]

    def test_array_format_with_array_value(self, tmp_path):
        json_file = tmp_path / "params.json"
        json_file.write_text(json.dumps([
            {"name": "LOOKUP", "value": [10, 20, 30], "unit": "", "description": "Lookup table"},
        ]))
        from consync.parsers.json_parser import parse_json
        result = parse_json(json_file)

        assert result[0].value == [10, 20, 30]
        assert result[0].description == "Lookup table"

    def test_nested_format_with_array_value(self, tmp_path):
        json_file = tmp_path / "params.json"
        json_file.write_text(json.dumps({
            "BRAKE_LEVELS": {"value": [25, 50, 75, 100], "unit": "bar", "description": "Levels"},
        }))
        from consync.parsers.json_parser import parse_json
        result = parse_json(json_file)

        assert result[0].value == [25, 50, 75, 100]
        assert result[0].unit == "bar"

    def test_mixed_int_float_becomes_float_array(self, tmp_path):
        json_file = tmp_path / "params.json"
        json_file.write_text(json.dumps({
            "MIXED": [1, 2.5, 3],
        }))
        from consync.parsers.json_parser import parse_json
        result = parse_json(json_file)

        assert result[0].value == [1.0, 2.5, 3.0]
        assert result[0].type == ConstantType.ARRAY_FLOAT


# ═══════════════════════════════════════════════════════════════════════════════
# C header renderer tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCHeaderArrayRendering:
    """Test C header renderer generates array declarations."""

    def test_int_array(self, tmp_path):
        out = tmp_path / "out.h"
        from consync.renderers.c_header import render_c_header

        constants = [
            Constant(name="THRESHOLDS", value=[50, 100, 150, 200, 250], unit="bar"),
        ]
        config = MappingConfig(source="test.csv", target="out.h", header_guard="OUT_H")
        render_c_header(constants, out, config=config)

        content = out.read_text()
        assert "THRESHOLDS[]" in content
        assert "{50, 100, 150, 200, 250}" in content
        assert "uint8_t" in content  # all values fit in uint8

    def test_float_array(self, tmp_path):
        out = tmp_path / "out.h"
        from consync.renderers.c_header import render_c_header

        constants = [
            Constant(name="GAINS", value=[1.5, 2.7, 0.3]),
        ]
        config = MappingConfig(source="test.csv", target="out.h", header_guard="OUT_H")
        render_c_header(constants, out, config=config)

        content = out.read_text()
        assert "double GAINS[]" in content
        assert "1.5" in content
        assert "2.7" in content

    def test_mixed_scalar_and_array(self, tmp_path):
        out = tmp_path / "out.h"
        from consync.renderers.c_header import render_c_header

        constants = [
            Constant(name="MAX_PRESSURE", value=250),
            Constant(name="THRESHOLDS", value=[50, 100, 150]),
            Constant(name="GAIN", value=1.45),
        ]
        config = MappingConfig(
            source="test.csv", target="out.h",
            header_guard="OUT_H", static_const=True,
        )
        render_c_header(constants, out, config=config)

        content = out.read_text()
        assert "static const" in content
        assert "MAX_PRESSURE" in content
        assert "THRESHOLDS[]" in content
        assert "GAIN" in content

    def test_large_int_array_picks_correct_type(self, tmp_path):
        out = tmp_path / "out.h"
        from consync.renderers.c_header import render_c_header

        constants = [
            Constant(name="BIG_IDS", value=[1000, 50000, 70000]),  # needs uint32_t
        ]
        config = MappingConfig(source="test.csv", target="out.h", header_guard="OUT_H")
        render_c_header(constants, out, config=config)

        content = out.read_text()
        assert "uint32_t" in content


# ═══════════════════════════════════════════════════════════════════════════════
# C# renderer tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCSharpArrayRendering:
    """Test C# renderer generates array declarations."""

    def test_int_array(self, tmp_path):
        out = tmp_path / "Out.cs"
        from consync.renderers.csharp import render_csharp

        constants = [
            Constant(name="THRESHOLDS", value=[50, 100, 150, 200, 250], unit="bar",
                     description="Brake thresholds"),
        ]
        config = MappingConfig(source="test.csv", target="Out.cs", namespace="ECU")
        render_csharp(constants, out, config=config)

        content = out.read_text()
        assert "public static readonly int[] THRESHOLDS" in content
        assert "{ 50, 100, 150, 200, 250 }" in content
        assert "Brake thresholds" in content

    def test_float_array(self, tmp_path):
        out = tmp_path / "Out.cs"
        from consync.renderers.csharp import render_csharp

        constants = [
            Constant(name="GAINS", value=[1.5, 2.7, 0.3]),
        ]
        config = MappingConfig(source="test.csv", target="Out.cs", namespace="ECU")
        render_csharp(constants, out, config=config)

        content = out.read_text()
        assert "public static readonly double[] GAINS" in content
        assert "1.5" in content

    def test_string_array(self, tmp_path):
        out = tmp_path / "Out.cs"
        from consync.renderers.csharp import render_csharp

        constants = [
            Constant(name="STATES", value=["IDLE", "RUNNING", "ERROR"]),
        ]
        config = MappingConfig(source="test.csv", target="Out.cs", namespace="ECU")
        render_csharp(constants, out, config=config)

        content = out.read_text()
        assert "public static readonly string[] STATES" in content
        assert '"IDLE"' in content
        assert '"RUNNING"' in content


# ═══════════════════════════════════════════════════════════════════════════════
# Python renderer tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPythonArrayRendering:
    """Test Python renderer generates list constants."""

    def test_int_array(self, tmp_path):
        out = tmp_path / "out.py"
        from consync.renderers.python_const import render_python

        constants = [
            Constant(name="THRESHOLDS", value=[50, 100, 150]),
        ]
        config = MappingConfig(source="test.csv", target="out.py")
        render_python(constants, out, config=config)

        content = out.read_text()
        assert "THRESHOLDS: list[int]" in content
        assert "[50, 100, 150]" in content

    def test_float_array(self, tmp_path):
        out = tmp_path / "out.py"
        from consync.renderers.python_const import render_python

        constants = [
            Constant(name="GAINS", value=[1.5, 2.7, 0.3]),
        ]
        config = MappingConfig(source="test.csv", target="out.py")
        render_python(constants, out, config=config)

        content = out.read_text()
        assert "GAINS: list[float]" in content
        assert "1.5" in content


# ═══════════════════════════════════════════════════════════════════════════════
# Rust renderer tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRustArrayRendering:
    """Test Rust renderer generates fixed-size array constants."""

    def test_int_array(self, tmp_path):
        out = tmp_path / "out.rs"
        from consync.renderers.rust_const import render_rust

        constants = [
            Constant(name="THRESHOLDS", value=[50, 100, 150]),
        ]
        config = MappingConfig(source="test.csv", target="out.rs")
        render_rust(constants, out, config=config)

        content = out.read_text()
        assert "pub const THRESHOLDS: [i64; 3] = [50, 100, 150];" in content

    def test_float_array(self, tmp_path):
        out = tmp_path / "out.rs"
        from consync.renderers.rust_const import render_rust

        constants = [
            Constant(name="GAINS", value=[1.5, 2.7]),
        ]
        config = MappingConfig(source="test.csv", target="out.rs")
        render_rust(constants, out, config=config)

        content = out.read_text()
        assert "pub const GAINS: [f64; 2]" in content
        assert "1.5" in content


# ═══════════════════════════════════════════════════════════════════════════════
# CSV renderer round-trip tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCSVArrayRoundTrip:
    """Test that arrays survive parse → render → parse cycle."""

    def test_roundtrip_int_array(self, tmp_path):
        # Write CSV with array
        csv1 = tmp_path / "input.csv"
        csv1.write_text(
            "name,value,unit,description\n"
            "THRESHOLDS,50|100|150|200|250,bar,Pressure thresholds\n"
            "SCALAR,42,,A scalar\n"
        )

        # Parse
        from consync.parsers.csv_parser import parse_csv
        from consync.renderers.csv_renderer import render_csv

        constants = parse_csv(csv1)
        assert constants[0].value == [50, 100, 150, 200, 250]

        # Render back to CSV
        csv2 = tmp_path / "output.csv"
        render_csv(constants, csv2)

        # Re-parse and verify
        constants2 = parse_csv(csv2)
        assert constants2[0].value == [50, 100, 150, 200, 250]
        assert constants2[1].value == 42

    def test_roundtrip_json_to_c(self, tmp_path):
        """JSON source with arrays → C header with array declarations."""
        json_file = tmp_path / "params.json"
        json_file.write_text(json.dumps({
            "MAX_PRESSURE": 250,
            "THRESHOLDS": [50, 100, 150, 200],
            "GAINS": [1.5, 2.7, 0.3],
        }))

        from consync.parsers.json_parser import parse_json
        from consync.renderers.c_header import render_c_header

        constants = parse_json(json_file)
        out_h = tmp_path / "out.h"
        config = MappingConfig(source="params.json", target="out.h", header_guard="OUT_H")
        render_c_header(constants, out_h, config=config)

        content = out_h.read_text()
        assert "MAX_PRESSURE" in content
        assert "THRESHOLDS[]" in content
        assert "{50, 100, 150, 200}" in content
        assert "double GAINS[]" in content


# ═══════════════════════════════════════════════════════════════════════════════
# End-to-end sync test with arrays
# ═══════════════════════════════════════════════════════════════════════════════


class TestEndToEndArraySync:
    """Test full sync with array constants."""

    def test_csv_to_c_with_arrays(self, tmp_path):
        """Full pipeline: CSV with arrays → C header."""
        csv_file = tmp_path / "params.csv"
        csv_file.write_text(
            "name,value,unit,description\n"
            "MAX_PRESSURE,250,bar,Max hydraulic pressure\n"
            "THRESHOLDS,50|100|150|200|250,bar,Brake thresholds\n"
            "PID_GAINS,1.5|2.7|0.3,,Controller gains\n"
        )

        # Write config
        config_yaml = tmp_path / ".consync.yaml"
        config_yaml.write_text(
            "mappings:\n"
            "  - source: params.csv\n"
            "    target: out.h\n"
            "    direction: source_to_target\n"
            "    header_guard: PARAMS_H\n"
            "    static_const: true\n"
            "    typed_ints: true\n"
        )

        from consync.sync import sync
        reports = sync(config_path=str(config_yaml))

        assert len(reports) == 1
        assert reports[0].count == 3

        out_h = tmp_path / "out.h"
        content = out_h.read_text()
        assert "MAX_PRESSURE" in content
        assert "THRESHOLDS[]" in content
        assert "{50, 100, 150, 200, 250}" in content
        assert "double PID_GAINS[]" in content
        assert "1.5" in content
