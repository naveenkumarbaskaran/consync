"""C struct table renderer — writes constants back into struct array initializer files.

This renderer performs **in-place updates** of numeric literal values within
an existing C struct table file, preserving:
  - File structure and formatting
  - Comments and labels
  - Preprocessor conditionals (#if/#elif/#endif)
  - Expression-based values (only literal numbers are updated)
  - Brace nesting and indentation

It does NOT generate a new file from scratch — it patches specific values
in the existing file based on row label + field index matching.
"""

from __future__ import annotations

import re
from pathlib import Path

from consync.models import Constant
from consync.renderers import register


# Regex to match C numeric literals with optional suffix
_NUMERIC_LITERAL_RE = re.compile(
    r"[+-]?"
    r"(?:0[xX][0-9a-fA-F]+|"
    r"\d+\.?\d*(?:[eE][+-]?\d+)?)"
    r"[fFlLuU]*"
)

_ROW_LABEL_RE = re.compile(r"/\*\s*(.+?)\s*\*/")


def _sanitize_label(label: str) -> str:
    """Convert a row label to the sanitized identifier form."""
    sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", label.strip())
    return sanitized.strip("_")


def _format_numeric(value: float | int, original_raw: str = "") -> str:
    """Format a numeric value back to C literal, preserving style of original.

    Preserves:
      1. Original exponent for scientific notation (E-3 stays E-3)
      2. Lowercase/uppercase 'e'/'E'
      3. Mantissa format (with/without decimal point)
      4. Precision (number of decimal digits)
      5. Exponent digit count (E-03 vs E-3)
    """
    if isinstance(value, int):
        if original_raw and original_raw.strip().startswith(("0x", "0X")):
            return f"0x{value:X}"
        suffix = ""
        if original_raw:
            # Preserve u/U suffix
            stripped = original_raw.strip()
            if stripped.endswith("u") or stripped.endswith("U"):
                suffix = stripped[-1]
        return f"{value}{suffix}"

    # Float value
    suffix = "F"  # default
    if original_raw:
        stripped = original_raw.strip()
        if stripped.endswith("f"):
            suffix = "f"
        elif stripped.endswith("F"):
            suffix = "F"
        elif stripped.endswith("L") or stripped.endswith("l"):
            suffix = stripped[-1]
        else:
            suffix = ""

    # Check if original used scientific notation
    if original_raw and ("e" in original_raw or "E" in original_raw):
        # Determine case of exponent character
        use_lowercase = "e" in original_raw and "E" not in original_raw
        exp_char = "e" if use_lowercase else "E"

        # Extract original exponent value
        orig_no_suffix = original_raw.strip().rstrip("fFlLuU")
        exp_match = re.search(r"[eE]([+-]?\d+)", orig_no_suffix)
        if exp_match:
            orig_exponent = int(exp_match.group(1))

            # Handle negative values
            sign = ""
            abs_value = value
            if value < 0:
                sign = "-"
                abs_value = abs(value)

            # Calculate new mantissa preserving the original exponent
            # value = mantissa * 10^exponent  =>  mantissa = value / 10^exponent
            if abs_value == 0:
                new_mantissa = 0.0
            else:
                new_mantissa = abs_value / (10 ** orig_exponent)

            # Determine mantissa format from original
            mantissa_part = orig_no_suffix.split("e")[0].split("E")[0]
            mantissa_part = mantissa_part.lstrip("+-")

            if "." in mantissa_part:
                decimal_digits = len(mantissa_part.split(".")[1])
                mantissa_str = f"{new_mantissa:.{decimal_digits}f}"
            else:
                # No decimal in original (like "1E-2")
                mantissa_str = f"{int(round(new_mantissa))}"

            # Preserve exponent format (E-03 vs E-3, leading zeros)
            exp_match_full = re.search(r"[eE]([+-]?)(\d+)", orig_no_suffix)
            if exp_match_full:
                exp_sign_char = exp_match_full.group(1)
                exp_digit_count = len(exp_match_full.group(2))
                if orig_exponent < 0:
                    exp_sign_str = "-"
                elif exp_sign_char == "+":
                    exp_sign_str = "+"
                else:
                    exp_sign_str = ""
                exp_abs = abs(orig_exponent)
                exp_str = f"{exp_sign_str}{exp_abs:0{exp_digit_count}d}"
            else:
                exp_str = f"{orig_exponent:+d}"

            formatted = f"{sign}{mantissa_str}{exp_char}{exp_str}"
            return f"{formatted}{suffix}"
        else:
            # Fallback (shouldn't happen if we got here)
            formatted = f"{value:E}"
            return f"{formatted}{suffix}"
    else:
        # Regular float notation (no scientific notation in original)
        if original_raw:
            orig_stripped = original_raw.strip().rstrip("fFlL")
            if "." in orig_stripped:
                decimal_digits = len(orig_stripped.split(".")[1])
                formatted = f"{value:.{decimal_digits}f}"
            else:
                formatted = (
                    str(int(round(value))) if value == int(value) else str(value)
                )
        else:
            formatted = str(value)
        return f"{formatted}{suffix}"


@register("c_struct_table")
def render_c_struct_table(
    constants: list[Constant],
    filepath: str | Path,
    config=None,
    **kwargs,
) -> None:
    """Render constants back into a C struct table file (in-place update).

    Only updates literal numeric values that match by row label and field index.
    Expression values and non-matching fields are left unchanged.

    When constants lack "raw" metadata (e.g., coming from Excel), the renderer
    first parses the existing C file to get current raw values, then uses those
    for pattern-based replacement — only updating values that actually changed.

    Args:
        constants: List of Constant objects (as produced by the parser).
        filepath: Path to the existing .c/.h file to update in place.
        config: MappingConfig (unused here but required by interface).
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(
            f"Cannot render c_struct_table: file not found: {filepath}. "
            f"This renderer only updates existing files in-place."
        )

    # Build a lookup: (variant, sanitized_label, field_index) → Constant
    updates: dict[tuple[str, str, int], Constant] = {}
    for c in constants:
        meta = c.metadata
        if not meta:
            continue
        if meta.get("is_expression"):
            continue  # Don't try to update expressions
        label = meta.get("row_label", "")
        field_idx = meta.get("field_index")
        variant = meta.get("variant", "")
        if label is not None and field_idx is not None:
            key = (variant, _sanitize_label(label), field_idx)
            updates[key] = c

    if not updates:
        return  # Nothing to update

    # If constants lack "raw" metadata, enrich them from the existing file
    has_raw = any(c.metadata.get("raw") for c in updates.values())
    if not has_raw:
        updates = _enrich_with_raw(updates, filepath, config)

    if not updates:
        return

    text = filepath.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    result_lines: list[str] = []

    # Track current variant section as we scan lines
    current_variant = ""
    # Detect variant from #if/#elif lines using the same logic as the parser
    variant_re = re.compile(r"#(?:if|elif)\s*\(.*?==\s*\w+?_(\w+)\s*\)")

    for line in lines:
        # Track variant sections
        variant_match = variant_re.search(line)
        if variant_match:
            current_variant = variant_match.group(1)

        # Check if this line has a row label and struct data
        label_match = _ROW_LABEL_RE.search(line)
        if label_match and ("{{" in line or ("{" in line and "}" in line)):
            label = label_match.group(1).strip()
            sanitized = _sanitize_label(label)

            # Check if we have any updates for this row in the current variant
            row_updates = {
                idx: c for (v, lbl, idx), c in updates.items()
                if lbl == sanitized and (v == current_variant or v == "")
            }
            if row_updates:
                line = _update_row_values(line, row_updates)

        result_lines.append(line)

    filepath.write_text("".join(result_lines), encoding="utf-8")


def _enrich_with_raw(
    updates: dict[tuple[str, str, int], Constant],
    filepath: Path,
    config=None,
) -> dict[tuple[str, str, int], Constant]:
    """Enrich update constants with 'raw' metadata from the existing C file.

    Parses the current C file to get raw values, then only keeps updates
    where the new value actually differs from the current value.
    Returns a filtered dict with raw metadata populated.
    """
    from consync.parsers.c_struct_table import parse_c_struct_table

    # Parse the file with parser options from config if available
    parser_opts = {}
    if config and hasattr(config, "parser_options"):
        parser_opts = config.parser_options or {}

    try:
        current_constants = parse_c_struct_table(filepath, **parser_opts)
    except Exception:
        return {}  # Can't parse — skip updates

    # Build lookup of current state: (variant, sanitized_label, field_index) → Constant
    current_map: dict[tuple[str, str, int], Constant] = {}
    for c in current_constants:
        meta = c.metadata
        if not meta:
            continue
        label = meta.get("row_label", "")
        field_idx = meta.get("field_index")
        variant = meta.get("variant", "")
        if label is not None and field_idx is not None:
            key = (variant, _sanitize_label(label), field_idx)
            current_map[key] = c

    # Filter: only keep updates where value actually changed
    # Enrich with raw metadata from current file
    enriched: dict[tuple[str, str, int], Constant] = {}
    for key, new_const in updates.items():
        current = current_map.get(key)
        if current is None:
            continue  # Not found in current file, skip

        raw = current.metadata.get("raw", "")
        if not raw:
            continue  # No raw value to match against

        # Check if value actually changed
        if _values_equal(new_const.value, current.value):
            continue  # Same value, no update needed

        # Create enriched constant with raw metadata
        enriched_meta = dict(new_const.metadata)
        enriched_meta["raw"] = raw
        enriched_const = Constant(
            name=new_const.name,
            value=new_const.value,
            unit=new_const.unit,
            description=new_const.description,
            metadata=enriched_meta,
        )
        enriched[key] = enriched_const

    return enriched


def _values_equal(a, b) -> bool:
    """Compare two values with tolerance for floating point."""
    if isinstance(a, float) and isinstance(b, float):
        if a == 0.0 and b == 0.0:
            return True
        if a == 0.0 or b == 0.0:
            return abs(a - b) < 1e-15
        return abs(a - b) / max(abs(a), abs(b)) < 1e-9
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


def _update_row_values(line: str, row_updates: dict[int, Constant]) -> str:
    """Update specific field values in a struct initializer row.

    Uses raw-pattern matching: finds the original literal text in the line
    and replaces with the new formatted value.
    """
    # Find where the data starts (first {{ after the label comment)
    brace_start = line.find("{{")
    if brace_start == -1:
        brace_start = line.find("{")
        if brace_start == -1:
            return line

    prefix = line[:brace_start]
    data_part = line[brace_start:]

    for field_idx, const in row_updates.items():
        raw_original = const.metadata.get("raw", "")
        if not raw_original or not isinstance(const.value, (int, float)):
            continue

        escaped = re.escape(raw_original)
        pattern = re.compile(r"(?<![a-zA-Z0-9_.])" + escaped + r"(?![a-zA-Z0-9_.])")
        new_value = _format_numeric(const.value, raw_original)
        data_part, count = pattern.subn(new_value, data_part, count=1)

    return prefix + data_part
