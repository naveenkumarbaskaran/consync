"""C/C++ header parser — reads const declarations from .h files.

Parses lines matching:
    const double NAME = VALUE;          /* unit | description */
    const float NAME = VALUE;           // description
    #define NAME VALUE                  /* unit | description */
    static const int NAME = VALUE;

Also handles:
    const double NAME = 1.234e-07;     (scientific notation)
    const uint32_t NAME = 0xFF;        (hex literals)
"""

from __future__ import annotations

import re
from pathlib import Path

from consync.models import Constant
from consync.parsers import register
from consync.precision import parse_number


# Patterns for C constant declarations
_CONST_PATTERN = re.compile(
    r"^\s*(?:static\s+)?(?:const(?:expr)?)\s+"
    r"(?:unsigned\s+|signed\s+)?"
    r"(?:double|float|int|long|uint\d+_t|int\d+_t|size_t)\s+"
    r"(\w+)\s*=\s*([^;]+);\s*"
    r"(?:/[/*]\s*(.*?)(?:\*/)?)?$"
)

# #define pattern
_DEFINE_PATTERN = re.compile(
    r"^\s*#define\s+(\w+)\s+([^\s/]+)\s*(?:/[/*]\s*(.*?)(?:\*/)?)?$"
)


@register("c_header")
def parse_c_header(filepath: str | Path, **kwargs) -> list[Constant]:
    """Parse constants from a C/C++ header file.

    Reads `const type NAME = VALUE;` and `#define NAME VALUE` declarations.
    Extracts unit and description from trailing comments (pipe-separated).
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Header file not found: {filepath}")

    text = filepath.read_text(encoding="utf-8")
    constants: list[Constant] = []

    for line in text.splitlines():
        const = _try_parse_line(line)
        if const is not None:
            constants.append(const)

    return constants


def _try_parse_line(line: str) -> Constant | None:
    """Try to parse a single line as a constant declaration."""
    # Try const declaration first
    m = _CONST_PATTERN.match(line)
    if m:
        return _build_constant(m.group(1), m.group(2), m.group(3))

    # Try #define
    m = _DEFINE_PATTERN.match(line)
    if m:
        return _build_constant(m.group(1), m.group(2), m.group(3))

    return None


def _build_constant(name: str, raw_value: str, comment: str | None) -> Constant | None:
    """Build a Constant from parsed components."""
    raw_value = raw_value.strip()
    # Strip C type suffixes (e.g., 1.0f, 100UL) but NOT from hex literals
    if not raw_value.startswith(("0x", "0X")):
        raw_value = raw_value.rstrip("fFlLuU")

    try:
        value = parse_number(raw_value)
    except (ValueError, IndexError):
        return None  # Skip non-numeric defines

    unit = ""
    description = ""
    if comment:
        comment = comment.strip().rstrip("*/").strip()
        parts = [p.strip() for p in comment.split("|", 1)]
        unit = parts[0] if len(parts) >= 1 else ""
        description = parts[1] if len(parts) >= 2 else ""

    return Constant(name=name, value=value, unit=unit, description=description)
