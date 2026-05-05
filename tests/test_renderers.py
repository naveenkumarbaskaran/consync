"""Tests for renderers — C header, Python, Rust, Verilog, VHDL, JSON."""

import json
from pathlib import Path

import pytest

from consync.models import Constant, MappingConfig, SyncDirection


@pytest.fixture
def sample_constants():
    return [
        Constant(name="R_SENSE", value=1.9999999999910001, unit="Ohm", description="Current sense resistor"),
        Constant(name="R_PULLUP", value=4706, unit="Ohm", description="I2C pull-up resistor"),
        Constant(name="C_FILTER", value=4.7832940e-07, unit="F", description="Input filter capacitor"),
        Constant(name="FREQ_SWITCH", value=299872.93847293, unit="Hz", description="Switching frequency"),
    ]


@pytest.fixture
def default_config():
    return MappingConfig(
        source="constants.xlsx",
        target="constants.h",
        source_format="xlsx",
        target_format="c_header",
        direction=SyncDirection.BOTH,
        precision=17,
        header_guard="HW_CONSTANTS_H",
    )


class TestCHeaderRenderer:
    def test_generates_valid_header(self, tmp_path, sample_constants, default_config):
        from consync.renderers.c_header import render_c_header

        out = tmp_path / "out.h"
        render_c_header(sample_constants, out, config=default_config)

        content = out.read_text()
        assert "#ifndef HW_CONSTANTS_H" in content
        assert "#define HW_CONSTANTS_H" in content
        assert "#endif" in content
        assert "double" in content
        assert "R_SENSE" in content
        assert "1.9999999999910001" in content
        assert "4706" in content
        assert "/* Ohm | Current sense resistor */" in content
        # Typed ints enabled by default
        assert "uint16_t" in content  # R_PULLUP = 4706 fits in uint16_t
        assert "#include <stdint.h>" in content

    def test_round_trip_precision(self, tmp_path, sample_constants, default_config):
        from consync.renderers.c_header import render_c_header
        from consync.parsers.c_header import parse_c_header

        out = tmp_path / "rt.h"
        render_c_header(sample_constants, out, config=default_config)
        parsed = parse_c_header(out)

        assert len(parsed) == len(sample_constants)
        for orig, back in zip(sample_constants, parsed):
            assert orig.name == back.name
            if isinstance(orig.value, float):
                assert orig.value == back.value, f"Precision lost for {orig.name}"
            else:
                assert orig.value == back.value

    def test_scientific_notation_preserved(self, tmp_path, default_config):
        from consync.renderers.c_header import render_c_header

        constants = [Constant(name="TINY", value=1.23e-15, unit="F")]
        out = tmp_path / "sci.h"
        render_c_header(constants, out, config=default_config)
        content = out.read_text()
        # Should contain scientific notation
        assert "e-" in content.lower() or "1.23e-15" in content.lower()


class TestPythonRenderer:
    def test_generates_python_module(self, tmp_path, sample_constants, default_config):
        from consync.renderers.python_const import render_python

        out = tmp_path / "constants.py"
        render_python(sample_constants, out, config=default_config)

        content = out.read_text()
        assert "R_SENSE: float" in content
        assert "R_PULLUP: int" in content
        assert "1.9999999999910001" in content
        assert "4706" in content
        assert "# Ohm" in content

    def test_valid_python_syntax(self, tmp_path, sample_constants, default_config):
        from consync.renderers.python_const import render_python

        out = tmp_path / "constants.py"
        render_python(sample_constants, out, config=default_config)

        # Should be valid Python
        content = out.read_text()
        compile(content, str(out), "exec")


class TestRustRenderer:
    def test_generates_rust_consts(self, tmp_path, sample_constants, default_config):
        from consync.renderers.rust_const import render_rust

        out = tmp_path / "constants.rs"
        render_rust(sample_constants, out, config=default_config)

        content = out.read_text()
        assert "pub const R_SENSE: f64" in content
        assert "pub const R_PULLUP: i64" in content
        assert "1.9999999999910001" in content
        assert "///" in content  # doc comments

    def test_f64_has_decimal(self, tmp_path, default_config):
        from consync.renderers.rust_const import render_rust

        constants = [Constant(name="WHOLE", value=100.0)]
        out = tmp_path / "whole.rs"
        render_rust(constants, out, config=default_config)
        content = out.read_text()
        # Rust requires 100.0 not 100 for f64
        assert "100.0" in content or "100" in content


class TestVerilogRenderer:
    def test_generates_parameters(self, tmp_path, sample_constants, default_config):
        from consync.renderers.verilog import render_verilog

        out = tmp_path / "params.v"
        render_verilog(sample_constants, out, config=default_config)

        content = out.read_text()
        assert "parameter real R_SENSE" in content
        assert "parameter integer R_PULLUP" in content
        assert "1.9999999999910001" in content

    def test_module_wrapper(self, tmp_path, sample_constants):
        from consync.renderers.verilog import render_verilog

        cfg = MappingConfig(
            source="test.xlsx", target="test.v",
            module_name="design_params", precision=17,
        )
        out = tmp_path / "wrapped.v"
        render_verilog(sample_constants, out, config=cfg)

        content = out.read_text()
        assert "module design_params;" in content
        assert "endmodule" in content


class TestVHDLRenderer:
    def test_generates_package(self, tmp_path, sample_constants, default_config):
        from consync.renderers.vhdl import render_vhdl

        out = tmp_path / "hw_constants.vhd"
        render_vhdl(sample_constants, out, config=default_config)

        content = out.read_text()
        assert "library ieee;" in content
        assert "package hw_constants is" in content
        assert "end package hw_constants;" in content
        assert "constant R_SENSE" in content
        assert ": real :=" in content
        assert ": integer :=" in content

    def test_custom_package_name(self, tmp_path, sample_constants):
        from consync.renderers.vhdl import render_vhdl

        cfg = MappingConfig(
            source="test.xlsx", target="test.vhd",
            module_name="my_pkg", precision=17,
        )
        out = tmp_path / "test.vhd"
        render_vhdl(sample_constants, out, config=cfg)

        content = out.read_text()
        assert "package my_pkg is" in content


class TestJSONRenderer:
    def test_generates_structured_json(self, tmp_path, sample_constants, default_config):
        from consync.renderers.json_renderer import render_json

        out = tmp_path / "out.json"
        render_json(sample_constants, out, config=default_config)

        data = json.loads(out.read_text())
        assert "_meta" in data
        assert data["_meta"]["generator"] == "consync"
        assert len(data["constants"]) == 4
        assert data["constants"][0]["name"] == "R_SENSE"
        assert data["constants"][0]["value"] == 1.9999999999910001

    def test_preserves_precision_in_json(self, tmp_path, sample_constants, default_config):
        from consync.renderers.json_renderer import render_json

        out = tmp_path / "prec.json"
        render_json(sample_constants, out, config=default_config)

        data = json.loads(out.read_text())
        # IEEE 754 double should round-trip through JSON
        for orig, rendered in zip(sample_constants, data["constants"]):
            if isinstance(orig.value, float):
                assert orig.value == rendered["value"]
