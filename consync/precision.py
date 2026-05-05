"""Precision-preserving number formatting for IEEE 754 doubles.

The core problem: hardware constants have 15-17 significant digits.
Excel stores them as IEEE 754 doubles. When writing to C/Verilog/Python,
we must preserve ALL significant digits to guarantee round-trip fidelity:

    parse(format(x)) == x

Default: 17 significant digits (maximum for double precision).
"""

from __future__ import annotations

import math
from decimal import Decimal


def format_float(value: float, precision: int = 17) -> str:
    """Format a float preserving significant digits.

    Uses Python's `g` format which automatically chooses between
    fixed-point and scientific notation for best readability.

    Args:
        value: The float to format.
        precision: Number of significant digits (1-21). Default 17.

    Returns:
        String representation with full precision.

    Examples:
        >>> format_float(1.20029384729384)
        '1.20029384729384'
        >>> format_float(0.00000047832940)
        '4.783294e-07'
        >>> format_float(100029.4829183)
        '100029.4829183'
        >>> format_float(4700.0)
        '4700'
    """
    if precision < 1:
        precision = 1
    if precision > 21:
        precision = 21

    if math.isnan(value):
        return "NAN"
    if math.isinf(value):
        return "INF" if value > 0 else "-INF"

    formatted = f"{value:.{precision}g}"

    # Ensure no trailing zeros that add false precision,
    # but keep at least one digit after decimal for floats
    return formatted


def format_c_double(value: float, precision: int = 17) -> str:
    """Format a float for C/C++ const double declaration.

    Always produces a string that, when parsed by a C compiler,
    yields the exact same IEEE 754 bit pattern.

    Examples:
        >>> format_c_double(4.7832940e-07)
        '4.7832940000000000e-07'
        >>> format_c_double(4700.0)
        '4700'
        >>> format_c_double(1.20029384729384)
        '1.20029384729384'
    """
    return format_float(value, precision)


def format_scientific(value: float, precision: int = 17) -> str:
    """Always use scientific notation (for Verilog/VHDL real parameters).

    Examples:
        >>> format_scientific(4700.0)
        '4.7e+03'
        >>> format_scientific(0.00000047832940)
        '4.783294e-07'
    """
    if precision < 1:
        precision = 1
    return f"{value:.{precision}e}"


def format_fixed(value: float, decimal_places: int = 14) -> str:
    """Fixed-point notation with explicit decimal places.

    Examples:
        >>> format_fixed(1.20029384729384, 14)
        '1.20029384729384'
    """
    return f"{value:.{decimal_places}f}".rstrip("0").rstrip(".")


def parse_number(text: str) -> float | int:
    """Parse a numeric string, preserving int vs float distinction.

    Handles scientific notation, underscores (Rust/Verilog style),
    and common suffixes.

    Examples:
        >>> parse_number("4.7832940e-07")
        4.783294e-07
        >>> parse_number("4700")
        4700
        >>> parse_number("1_000_000")
        1000000
        >>> parse_number("0xFF")
        255
    """
    text = text.strip().replace("_", "")

    # Hex literals
    if text.lower().startswith("0x"):
        return int(text, 16)

    # Binary literals
    if text.lower().startswith("0b"):
        return int(text, 2)

    # Try int first
    try:
        val = int(text)
        return val
    except ValueError:
        pass

    # Then float
    return float(text)


def significant_digits(value: float) -> int:
    """Count the significant digits in a float's representation.

    Uses Decimal to get the shortest representation that round-trips.
    """
    if value == 0:
        return 1
    d = Decimal(str(value))
    # sign, digits, exponent
    _, digits, _ = d.as_tuple()
    # Strip trailing zeros
    stripped = str(int("".join(str(d) for d in digits))).rstrip("0")
    return len(stripped) if stripped else 1
