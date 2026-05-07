"""Tests for c_struct_table parser — generic C struct array initializer parsing."""

import textwrap
from pathlib import Path

import pytest

from consync.parsers.c_struct_table import (
    parse_c_struct_table,
    _auto_detect_table_var,
    _auto_detect_fields,
    _auto_detect_variants,
    _flatten_values,
    _extract_row_data,
    _find_variant_block,
    _find_table_block,
)


@pytest.fixture
def tmp_file(tmp_path):
    """Helper to create temp files with content."""
    def _create(filename: str, content: str) -> Path:
        p = tmp_path / filename
        p.write_text(textwrap.dedent(content))
        return p
    return _create


# ============================================================
# _flatten_values — brace flattening
# ============================================================

class TestFlattenValues:
    def test_simple_scalars(self):
        result = _flatten_values("1.0F, 2.0F, 3.0F")
        assert result == ["1.0F", "2.0F", "3.0F"]

    def test_nested_braces(self):
        result = _flatten_values("{1.0F, 2.0F}, 3.0F")
        assert result == ["1.0F", "2.0F", "3.0F"]

    def test_deep_nesting(self):
        result = _flatten_values("{1.0F, {2.0F, 3.0F}}, 4.0F")
        assert result == ["1.0F", "2.0F", "3.0F", "4.0F"]

    def test_mixed_scalars_and_braces(self):
        result = _flatten_values("1.0F, {2.0F, 3.0F}, 4.0F, {5.0F}")
        assert result == ["1.0F", "2.0F", "3.0F", "4.0F", "5.0F"]

    def test_expression_values(self):
        result = _flatten_values("0.25F / (float32)NF_PSC_FREQUENCY, 300.0F")
        assert len(result) == 2
        assert "NF_PSC_FREQUENCY" in result[0]
        assert result[1] == "300.0F"

    def test_empty(self):
        result = _flatten_values("")
        assert result == []


# ============================================================
# _extract_row_data
# ============================================================

class TestExtractRowData:
    def test_labeled_row(self):
        line = '/* Motor A */ {{1.0F, 2.0F}, 3.0F},'
        result = _extract_row_data(line)
        assert result is not None
        label, content = result
        assert label == "Motor A"
        assert "1.0F" in content

    def test_no_label(self):
        line = '{{1.0F, 2.0F}, 3.0F},'
        result = _extract_row_data(line)
        assert result is not None
        label, content = result
        assert label == ""

    def test_no_braces(self):
        line = "// just a comment"
        result = _extract_row_data(line)
        assert result is None

    def test_unbalanced_braces_returns_none(self):
        line = '/* X */ {{1.0F, 2.0F'  # no closing
        result = _extract_row_data(line)
        assert result is None


# ============================================================
# Auto-detection functions
# ============================================================

class TestAutoDetectTableVar:
    def test_static_const(self):
        text = 'static const MyType MyTable[10] = {\n'
        assert _auto_detect_table_var(text) == "MyTable"

    def test_just_const(self):
        text = 'const CalibData_t SensorLUT[NUM] = {\n'
        assert _auto_detect_table_var(text) == "SensorLUT"

    def test_no_table(self):
        text = 'int x = 5;\n'
        assert _auto_detect_table_var(text) is None

    def test_picks_first(self):
        text = 'static const A_t TableA[2] = {\n};\nstatic const B_t TableB[3] = {\n};'
        assert _auto_detect_table_var(text) == "TableA"


class TestAutoDetectFields:
    def test_finds_header_comment(self):
        text = textwrap.dedent("""\
            /* gain  offset  threshold */
            /* Sensor_A */ {{1.0F, 2.0F, 3.0F}},
        """)
        result = _auto_detect_fields(text)
        assert result == ["gain", "offset", "threshold"]

    def test_ignores_non_header_comments(self):
        text = textwrap.dedent("""\
            /* This is a copyright notice */
            /* gain  offset  threshold */
            /* Sensor_A */ {{1.0F, 2.0F, 3.0F}},
        """)
        # Should pick the last comment before data row
        result = _auto_detect_fields(text)
        assert result == ["gain", "offset", "threshold"]

    def test_no_header_comment(self):
        text = textwrap.dedent("""\
            /* Sensor_A */ {{1.0F, 2.0F}},
        """)
        result = _auto_detect_fields(text)
        assert result is None

    def test_comma_separated_fields(self):
        text = textwrap.dedent("""\
            /*  R_Phase,  L_d,  L_q,  Psi  */
            /* Row1 */ {{1.0F, 2.0F, 3.0F, 4.0F}},
        """)
        result = _auto_detect_fields(text)
        assert result == ["R_Phase", "L_d", "L_q", "Psi"]


class TestAutoDetectVariants:
    def test_finds_variants(self):
        text = textwrap.dedent("""\
            #if (RBFS_Motor == RBFS_Motor_BWA)
            // stuff
            #elif (RBFS_Motor == RBFS_Motor_EMB)
            // stuff
            #elif (RBFS_Motor == RBFS_Motor_DPB)
            // stuff
            #endif
        """)
        result = _auto_detect_variants(text)
        assert result == ["BWA", "EMB", "DPB"]

    def test_no_variants(self):
        text = "int x = 5;\n"
        result = _auto_detect_variants(text)
        assert result == []

    def test_ignores_unrelated_ifdefs(self):
        text = textwrap.dedent("""\
            #if (PRODUCT == PRODUCT_A)
            #elif (PRODUCT == PRODUCT_B)
            #elif (PRODUCT == PRODUCT_C)
            #endif
            #if (FEATURE == FEATURE_On)
            #endif
        """)
        # Should return the chain with most alternatives (PRODUCT: 3 vs FEATURE: 1)
        result = _auto_detect_variants(text)
        assert result == ["A", "B", "C"]


# ============================================================
# _find_variant_block
# ============================================================

class TestFindVariantBlock:
    def test_finds_block(self):
        text = textwrap.dedent("""\
            #if (X == X_A)
            line_a1
            line_a2
            #elif (X == X_B)
            line_b1
            line_b2
            #endif
        """)
        result = _find_variant_block(text, "A")
        assert "line_a1" in result
        assert "line_a2" in result
        assert "line_b1" not in result

    def test_finds_elif_block(self):
        text = textwrap.dedent("""\
            #if (X == X_A)
            line_a
            #elif (X == X_B)
            line_b
            #elif (X == X_C)
            line_c
            #endif
        """)
        result = _find_variant_block(text, "B")
        assert "line_b" in result
        assert "line_a" not in result
        assert "line_c" not in result

    def test_variant_not_found(self):
        text = "#if (X == X_A)\n#endif\n"
        result = _find_variant_block(text, "Z")
        assert result is None


# ============================================================
# _find_table_block
# ============================================================

class TestFindTableBlock:
    def test_finds_named_table(self):
        text = textwrap.dedent("""\
            int x = 5;
            static const Foo MyLUT[3] = {
                {1, 2},
                {3, 4},
            };
            int y = 6;
        """)
        result = _find_table_block(text, "MyLUT")
        assert "MyLUT" in result
        assert "{1, 2}" in result
        assert "int y" not in result

    def test_auto_find_first_table(self):
        text = textwrap.dedent("""\
            static const Bar Table1[2] = {
                {10, 20},
            };
        """)
        result = _find_table_block(text, None)
        assert "Table1" in result


# ============================================================
# Full parser — parse_c_struct_table
# ============================================================

class TestParseCStructTable:
    def test_simple_table_no_variants(self, tmp_file):
        f = tmp_file("simple.c", """\
            static const Calib_t CalibTable[3] = {
                /* gain  offset  limit */
                /* Sensor_A */ {{1.5F, 2.0F}, 100.0F},
                /* Sensor_B */ {{1.6F, 2.1F}, 200.0F},
                /* Sensor_C */ {{1.7F, 2.2F}, 300.0F},
            };
        """)
        result = parse_c_struct_table(f)
        assert len(result) == 9  # 3 rows × 3 fields
        # Check first row
        assert result[0].name == "Sensor_A__gain"
        assert result[0].value == 1.5
        assert result[1].name == "Sensor_A__offset"
        assert result[1].value == 2.0
        assert result[2].name == "Sensor_A__limit"
        assert result[2].value == 100.0
        # Check metadata
        assert result[0].metadata["row_label"] == "Sensor_A"
        assert result[0].metadata["field"] == "gain"

    def test_explicit_fields(self, tmp_file):
        f = tmp_file("explicit.c", """\
            static const X_t data[2] = {
                /* A */ {{10, 20}},
                /* B */ {{30, 40}},
            };
        """)
        result = parse_c_struct_table(f, fields=["alpha", "beta"])
        assert result[0].name == "A__alpha"
        assert result[1].name == "A__beta"
        assert result[2].name == "B__alpha"

    def test_auto_detect_table_var(self, tmp_file):
        f = tmp_file("auto_table.c", """\
            int unrelated = 5;
            static const MyStruct LUT[2] = {
                /* R1 */ {{1.0F, 2.0F}},
                /* R2 */ {{3.0F, 4.0F}},
            };
            int other = 6;
        """)
        result = parse_c_struct_table(f, fields=["x", "y"])
        assert len(result) == 4
        assert result[0].value == 1.0
        assert result[3].value == 4.0

    def test_variant_selection(self, tmp_file):
        f = tmp_file("variants.c", """\
            static const Foo_t Table[2] = {
            #if (CFG == CFG_Alpha)
                /* x  y */
                /* R1 */ {{1.0F, 2.0F}},
                /* R2 */ {{3.0F, 4.0F}},
            #elif (CFG == CFG_Beta)
                /* x  y */
                /* R1 */ {{10.0F, 20.0F}},
                /* R2 */ {{30.0F, 40.0F}},
            #endif
            };
        """)
        alpha = parse_c_struct_table(f, variant="Alpha")
        assert len(alpha) == 4
        assert alpha[0].value == 1.0

        beta = parse_c_struct_table(f, variant="Beta")
        assert len(beta) == 4
        assert beta[0].value == 10.0

    def test_variant_all_mode(self, tmp_file):
        f = tmp_file("all.c", """\
            static const Bar_t T[1] = {
            #if (P == P_X)
                /* a  b */
                /* Row1 */ {{1.0F, 2.0F}},
            #elif (P == P_Y)
                /* a  b */
                /* Row1 */ {{3.0F, 4.0F}},
            #endif
            };
        """)
        result = parse_c_struct_table(f, variant="all")
        assert len(result) == 4  # 2 variants × 1 row × 2 fields
        # Check variant metadata
        x_consts = [c for c in result if c.metadata.get("variant") == "X"]
        y_consts = [c for c in result if c.metadata.get("variant") == "Y"]
        assert len(x_consts) == 2
        assert len(y_consts) == 2
        assert x_consts[0].value == 1.0
        assert y_consts[0].value == 3.0

    def test_boolean_values(self, tmp_file):
        f = tmp_file("bools.c", """\
            static const S_t T[2] = {
                /* flag  count */
                /* A */ {{TRUE, 5u}},
                /* B */ {{FALSE, 10u}},
            };
        """)
        result = parse_c_struct_table(f)
        assert result[0].value == "TRUE"
        assert result[1].value == 5
        assert result[2].value == "FALSE"
        assert result[3].value == 10

    def test_macro_references(self, tmp_file):
        f = tmp_file("macros.c", """\
            static const M_t T[1] = {
                /* val  mode */
                /* R1 */ {{1.0F, MY_MACRO}},
            };
        """)
        result = parse_c_struct_table(f)
        assert result[0].value == 1.0
        assert result[1].value == "MY_MACRO"
        assert result[1].metadata["is_expression"] is True

    def test_expression_values(self, tmp_file):
        f = tmp_file("expr.c", """\
            static const E_t T[1] = {
                /* kp  ki */
                /* R1 */ {{0.5F, 0.25F / (float32)FREQ}},
            };
        """)
        result = parse_c_struct_table(f)
        assert result[0].value == 0.5
        assert "FREQ" in result[1].value  # expression kept as string
        assert result[1].metadata["is_expression"] is True

    def test_hex_and_unsigned(self, tmp_file):
        f = tmp_file("hex.c", """\
            static const H_t T[1] = {
                /* addr  count */
                /* R1 */ {{0xFF, 5u}},
            };
        """)
        result = parse_c_struct_table(f)
        assert result[0].value == 255  # 0xFF
        assert result[1].value == 5

    def test_scientific_notation(self, tmp_file):
        f = tmp_file("sci.c", """\
            static const S_t T[1] = {
                /* r  l */
                /* R1 */ {{21.53E-3F, 28.18E-6F}},
            };
        """)
        result = parse_c_struct_table(f)
        assert abs(result[0].value - 0.02153) < 1e-10
        assert abs(result[1].value - 2.818e-5) < 1e-15

    def test_fallback_field_names(self, tmp_file):
        """When no header comment exists, fields become field_0, field_1..."""
        f = tmp_file("no_header.c", """\
            static const Z_t T[1] = {
                /* R1 */ {{1.0F, 2.0F, 3.0F}},
            };
        """)
        result = parse_c_struct_table(f)
        assert result[0].name == "R1__field_0"
        assert result[1].name == "R1__field_1"
        assert result[2].name == "R1__field_2"

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_c_struct_table(tmp_path / "nonexistent.c")

    def test_variant_not_found(self, tmp_file):
        f = tmp_file("missing_var.c", """\
            static const X_t T[1] = {
            #if (P == P_A)
                /* R1 */ {{1.0F}},
            #endif
            };
        """)
        with pytest.raises(ValueError, match="not found"):
            parse_c_struct_table(f, variant="Z")

    def test_deep_nesting_3_levels(self, tmp_file):
        f = tmp_file("deep.c", """\
            static const D_t T[1] = {
                /* a  b  c  d */
                /* R1 */ {{{1.0F, {2.0F, 3.0F}}, 4.0F}},
            };
        """)
        result = parse_c_struct_table(f)
        assert len(result) == 4
        assert result[0].value == 1.0
        assert result[1].value == 2.0
        assert result[2].value == 3.0
        assert result[3].value == 4.0

    def test_no_row_label_uses_counter(self, tmp_file):
        f = tmp_file("nolabel.c", """\
            static const N_t T[2] = {
                /* x  y  z */
                {{1.0F, 2.0F, 3.0F}},
                {{4.0F, 5.0F, 6.0F}},
            };
        """)
        result = parse_c_struct_table(f)
        # Auto-detects fields from header comment
        assert result[0].name == "row_0__x"
        assert result[3].name == "row_1__x"

    def test_label_sanitization(self, tmp_file):
        f = tmp_file("sanitize.c", """\
            static const S_t T[1] = {
                /* alpha  beta  gamma */
                /* Motor A/B (v2) */ {{1.0F, 2.0F, 3.0F}},
            };
        """)
        result = parse_c_struct_table(f)
        # Special chars in label → underscore, fields from header comment
        assert result[0].name == "Motor_A_B_v2__alpha"
        assert result[1].name == "Motor_A_B_v2__beta"
