"""Tests for embedded/ECU-specific features: #define, static const, typed ints, C#."""

from pathlib import Path

import pytest

from consync.models import Constant, MappingConfig, SyncDirection


@pytest.fixture
def ecu_constants():
    """Typical ECU/braking system constants."""
    return [
        Constant(name="CAN_BAUD_RATE", value=500000, unit="bps", description="CAN bus speed"),
        Constant(name="BRAKE_PRESSURE_MAX", value=180, unit="bar", description="Max hydraulic pressure"),
        Constant(name="WHEEL_SPEED_THRESHOLD", value=0.5, unit="m/s", description="ABS trigger threshold"),
        Constant(name="SENSOR_OFFSET", value=-127, unit="mV", description="Hall sensor offset"),
        Constant(name="REG_CTRL", value=0xFF, unit="", description="Control register address"),
        Constant(name="TICK_PERIOD_US", value=4.7832940e-07, unit="s", description="Timer tick"),
        Constant(name="GAIN_KP", value=1.9999999999910001, unit="", description="Proportional gain"),
    ]


class TestTypedInts:
    """Feature 2: auto-select uint32_t/int32_t/uint16_t/int16_t/uint8_t/int8_t."""

    def test_uint8_for_small_positive(self, tmp_path):
        from consync.renderers.c_header import render_c_header

        constants = [Constant(name="LED_BRIGHT", value=200)]
        cfg = MappingConfig(source="t.csv", target="t.h", typed_ints=True)
        out = tmp_path / "t.h"
        render_c_header(constants, out, config=cfg)
        content = out.read_text()
        assert "uint8_t" in content
        assert "200U" in content

    def test_uint16_for_medium_positive(self, tmp_path):
        from consync.renderers.c_header import render_c_header

        constants = [Constant(name="BAUD", value=9600)]
        cfg = MappingConfig(source="t.csv", target="t.h", typed_ints=True)
        out = tmp_path / "t.h"
        render_c_header(constants, out, config=cfg)
        content = out.read_text()
        assert "uint16_t" in content

    def test_uint32_for_large_positive(self, tmp_path):
        from consync.renderers.c_header import render_c_header

        constants = [Constant(name="CAN_BAUD", value=500000)]
        cfg = MappingConfig(source="t.csv", target="t.h", typed_ints=True)
        out = tmp_path / "t.h"
        render_c_header(constants, out, config=cfg)
        content = out.read_text()
        assert "uint32_t" in content
        assert "500000U" in content

    def test_int8_for_small_negative(self, tmp_path):
        from consync.renderers.c_header import render_c_header

        constants = [Constant(name="OFFSET", value=-100)]
        cfg = MappingConfig(source="t.csv", target="t.h", typed_ints=True)
        out = tmp_path / "t.h"
        render_c_header(constants, out, config=cfg)
        content = out.read_text()
        assert "int8_t" in content

    def test_int32_for_large_negative(self, tmp_path):
        from consync.renderers.c_header import render_c_header

        constants = [Constant(name="BIG_NEG", value=-100000)]
        cfg = MappingConfig(source="t.csv", target="t.h", typed_ints=True)
        out = tmp_path / "t.h"
        render_c_header(constants, out, config=cfg)
        content = out.read_text()
        assert "int32_t" in content

    def test_typed_ints_disabled(self, tmp_path):
        from consync.renderers.c_header import render_c_header

        constants = [Constant(name="REG", value=255)]
        cfg = MappingConfig(source="t.csv", target="t.h", typed_ints=False)
        out = tmp_path / "t.h"
        render_c_header(constants, out, config=cfg)
        content = out.read_text()
        assert "uint8_t" not in content
        assert "const int" in content

    def test_stdint_include_present(self, tmp_path, ecu_constants):
        from consync.renderers.c_header import render_c_header

        cfg = MappingConfig(source="t.csv", target="t.h", typed_ints=True)
        out = tmp_path / "t.h"
        render_c_header(ecu_constants, out, config=cfg)
        content = out.read_text()
        assert "#include <stdint.h>" in content


class TestDefineStyle:
    """Feature 1: #define output mode instead of const declarations."""

    def test_define_output(self, tmp_path, ecu_constants):
        from consync.renderers.c_header import render_c_header

        cfg = MappingConfig(source="t.csv", target="t.h", output_style="define")
        out = tmp_path / "t.h"
        render_c_header(ecu_constants, out, config=cfg)
        content = out.read_text()

        # Should use #define, not const
        assert "#define CAN_BAUD_RATE" in content
        assert "const" not in content.split("#endif")[0].split("#define")[0]  # no const decls
        # Values wrapped in parens
        assert "(500000U)" in content
        assert "(0.5)" in content or "(5." in content
        # Comments still present
        assert "/* bps | CAN bus speed */" in content

    def test_define_no_stdint(self, tmp_path):
        from consync.renderers.c_header import render_c_header

        constants = [Constant(name="X", value=42)]
        cfg = MappingConfig(source="t.csv", target="t.h", output_style="define")
        out = tmp_path / "t.h"
        render_c_header(constants, out, config=cfg)
        content = out.read_text()
        # #define mode doesn't need stdint.h
        assert "#include <stdint.h>" not in content


class TestStaticConst:
    """Feature 4: static const to avoid linker duplicate symbols."""

    def test_static_const_prefix(self, tmp_path, ecu_constants):
        from consync.renderers.c_header import render_c_header

        cfg = MappingConfig(source="t.csv", target="t.h", static_const=True)
        out = tmp_path / "t.h"
        render_c_header(ecu_constants, out, config=cfg)
        content = out.read_text()
        # Every const line should start with "static const"
        for line in content.splitlines():
            if line.startswith("const "):
                pytest.fail(f"Found non-static const: {line}")
        assert "static const" in content

    def test_non_static_by_default(self, tmp_path):
        from consync.renderers.c_header import render_c_header

        constants = [Constant(name="X", value=1.0)]
        cfg = MappingConfig(source="t.csv", target="t.h", static_const=False)
        out = tmp_path / "t.h"
        render_c_header(constants, out, config=cfg)
        content = out.read_text()
        assert "static const" not in content
        assert "const double" in content


class TestCSharpRenderer:
    """Feature 3: C# renderer for HIL/tooling code."""

    def test_generates_valid_class(self, tmp_path, ecu_constants):
        from consync.renderers.csharp import render_csharp

        cfg = MappingConfig(
            source="t.csv", target="t.cs",
            namespace="Bosch.Braking", module_name="EcuConstants",
        )
        out = tmp_path / "out.cs"
        render_csharp(ecu_constants, out, config=cfg)
        content = out.read_text()

        assert "namespace Bosch.Braking" in content
        assert "public static class EcuConstants" in content
        assert "public const int CAN_BAUD_RATE = 500000;" in content
        assert "public const double WHEEL_SPEED_THRESHOLD = 0.5;" in content
        assert "/// <summary>" in content

    def test_typed_ints_in_csharp(self, tmp_path):
        from consync.renderers.csharp import render_csharp

        constants = [
            Constant(name="BIG", value=3000000000),  # > int32 max
            Constant(name="SMALL", value=42),
        ]
        cfg = MappingConfig(source="t.csv", target="t.cs", typed_ints=True)
        out = tmp_path / "t.cs"
        render_csharp(constants, out, config=cfg)
        content = out.read_text()
        assert "uint" in content  # 3B needs uint
        assert "public const int SMALL = 42;" in content

    def test_xml_doc_comments(self, tmp_path):
        from consync.renderers.csharp import render_csharp

        constants = [Constant(name="P_MAX", value=180, unit="bar", description="Max pressure")]
        cfg = MappingConfig(source="t.csv", target="t.cs")
        out = tmp_path / "t.cs"
        render_csharp(constants, out, config=cfg)
        content = out.read_text()
        assert "/// <summary>Max pressure (bar)</summary>" in content

    def test_valid_csharp_syntax(self, tmp_path, ecu_constants):
        """Basic syntax check — braces balanced, semicolons present."""
        from consync.renderers.csharp import render_csharp

        cfg = MappingConfig(source="t.csv", target="t.cs")
        out = tmp_path / "t.cs"
        render_csharp(ecu_constants, out, config=cfg)
        content = out.read_text()
        assert content.count("{") == content.count("}")
        # Every const line has semicolon
        for line in content.splitlines():
            if "public const" in line:
                assert line.rstrip().endswith(";")

    def test_negative_int(self, tmp_path):
        from consync.renderers.csharp import render_csharp

        constants = [Constant(name="OFFSET", value=-127)]
        cfg = MappingConfig(source="t.csv", target="t.cs", typed_ints=True)
        out = tmp_path / "t.cs"
        render_csharp(constants, out, config=cfg)
        content = out.read_text()
        assert "public const int OFFSET = -127;" in content


class TestECUEndToEnd:
    """End-to-end: CSV → C header with ECU-typical config."""

    def test_full_ecu_flow(self, tmp_path):
        import textwrap
        from consync.sync import sync

        # Create config
        config = tmp_path / ".consync.yaml"
        config.write_text(textwrap.dedent("""\
            mappings:
              - source: ecu_params.csv
                target: ecu_params.h
                direction: source_to_target
                precision: 17
                header_guard: ECU_PARAMS_H
                output_style: const
                static_const: true
                typed_ints: true
                prefix: ECU_
        """))

        # Create source CSV
        csv_file = tmp_path / "ecu_params.csv"
        csv_file.write_text(
            "Name,Value,Unit,Description\n"
            "CAN_BAUD,500000,bps,CAN bus bitrate\n"
            "BRAKE_P_MAX,180,bar,Max brake pressure\n"
            "ABS_THRESHOLD,0.5,m/s,ABS activation speed\n"
            "SENSOR_OFFSET,-127,mV,Hall sensor zero offset\n"
        )

        reports = sync(config_path=config)
        assert reports[0].count == 4

        content = (tmp_path / "ecu_params.h").read_text()
        assert "#ifndef ECU_PARAMS_H" in content
        assert "static const" in content
        assert "uint32_t" in content  # 500000
        assert "uint8_t" in content  # 180
        assert "ECU_CAN_BAUD" in content  # prefix applied
        assert "ECU_SENSOR_OFFSET" in content
        assert "#include <stdint.h>" in content
