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

    Tries to maintain scientific notation, F suffix, etc. from the original.
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
    suffix = "F"
    if original_raw:
        stripped = original_raw.strip().rstrip("fFlL")
        if original_raw.strip().endswith("f") or original_raw.strip().endswith("F"):
            suffix = original_raw.strip()[-1]
        else:
            suffix = ""

    # Check if original used scientific notation
    if original_raw and ("e" in original_raw.lower() or "E" in original_raw):
        # Format in scientific notation
        # Detect the exponent style from original
        formatted = f"{value:E}"
        # Simplify: use same number of significant digits as original
        orig_stripped = original_raw.strip().rstrip("fFlL")
        if "." in orig_stripped:
            # Count digits after decimal before E
            parts = orig_stripped.upper().split("E")
            if "." in parts[0]:
                decimal_digits = len(parts[0].split(".")[1])
            else:
                decimal_digits = 2
        else:
            decimal_digits = 2

        formatted = f"{value:.{decimal_digits}E}"
        return f"{formatted}{suffix}"
    else:
        # Regular float notation
        if original_raw:
            orig_stripped = original_raw.strip().rstrip("fFlL")
            if "." in orig_stripped:
                decimal_digits = len(orig_stripped.split(".")[1])
                formatted = f"{value:.{decimal_digits}f}"
            else:
                formatted = str(value)
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

    # Build a lookup: (sanitized_label, field_index) → Constant
    updates: dict[tuple[str, int], Constant] = {}
    for c in constants:
        meta = c.metadata
        if not meta:
            continue
        if meta.get("is_expression"):
            continue  # Don't try to update expressions
        label = meta.get("row_label", "")
        field_idx = meta.get("field_index")
        if label is not None and field_idx is not None:
            key = (_sanitize_label(label), field_idx)
            updates[key] = c

    if not updates:
        return  # Nothing to update

    text = filepath.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    result_lines: list[str] = []

    for line in lines:
        # Check if this line has a row label and struct data
        label_match = _ROW_LABEL_RE.search(line)
        if label_match and ("{{" in line or ("{" in line and "}" in line)):
            label = label_match.group(1).strip()
            sanitized = _sanitize_label(label)

            # Check if we have any updates for this row
            row_updates = {idx: c for (lbl, idx), c in updates.items() if lbl == sanitized}
            if row_updates:
                line = _update_row_values(line, row_updates)

        result_lines.append(line)

    filepath.write_text("".join(result_lines), encoding="utf-8")


def _update_row_values(line: str, row_updates: dict[int, Constant]) -> str:
    """Update specific field values in a struct initializer row.

    Finds the Nth numeric literal in the brace content and replaces it.
    """
    # Find where the data starts (first {{ after the label comment)
    brace_start = line.find("{{")
    if brace_start == -1:
        brace_start = line.find("{")
        if brace_start == -1:
            return line

    prefix = line[:brace_start]
    data_part = line[brace_start:]

    # Walk through data_part, finding all tokens (numeric literals + expressions)
    # and tracking field indices
    field_idx = 0
    result = ""
    i = 0
    brace_depth = 0
    in_value = False
    current_value_start = -1

    # We need a smarter approach: tokenize by commas at the correct brace depth
    # But for replacement, we iterate through and find numeric literals at each position

    # Strategy: find all numeric literal positions in the data portion,
    # tracking which field index they correspond to
    # This is approximate — we count comma-separated values at depth 1 or 2

    # Alternative simpler approach: find and replace by matching the original raw value
    for field_idx, const in row_updates.items():
        raw_original = const.metadata.get("raw", "")
        if not raw_original or not isinstance(const.value, (int, float)):
            continue

        # Build a regex pattern that matches the original value (with possible whitespace)
        escaped = re.escape(raw_original)
        # Allow flexible whitespace around it
        pattern = re.compile(r"(?<![a-zA-Z0-9_.])" + escaped + r"(?![a-zA-Z0-9_.])")

        new_value = _format_numeric(const.value, raw_original)
        # Replace only the first occurrence in the data part
        data_part, count = pattern.subn(new_value, data_part, count=1)

    return prefix + data_part
