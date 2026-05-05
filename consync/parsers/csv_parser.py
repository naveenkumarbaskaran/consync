"""CSV parser — reads constants from comma/tab-separated files.

Expected format:
  Row 1: Header (Name, Value, Unit, Description)
  Row 2+: Data

Auto-detects delimiter (comma, tab, semicolon).

Array values are supported using pipe (|) or semicolon separation within the
value cell:
    THRESHOLDS,"50|100|150|200|250",bar,Brake pressure thresholds
    GAINS,"1.0|2.5|3.7",,PID gain table
"""

from __future__ import annotations

import csv
from pathlib import Path

from consync.models import Constant
from consync.parsers import register
from consync.precision import parse_number


def _parse_value(raw: str) -> float | int | str | list[int] | list[float] | list[str]:
    """Parse a value cell, detecting arrays (pipe or semicolon-separated).

    Returns a list if the value contains | or ; delimiters with multiple items.
    Otherwise returns a scalar.
    """
    # Detect array delimiter — pipes first, then semicolons (if not the CSV delimiter itself)
    for delim in ("|", ";"):
        if delim in raw:
            parts = [p.strip() for p in raw.split(delim) if p.strip()]
            if len(parts) >= 2:
                return _parse_array_parts(parts)

    # Scalar
    try:
        return parse_number(raw)
    except (ValueError, IndexError):
        return raw


def _parse_array_parts(parts: list[str]) -> list[int] | list[float] | list[str]:
    """Parse a list of string parts into a typed array."""
    # Try all-int first
    try:
        return [int(p, 16) if p.lower().startswith("0x") else int(p) for p in parts]
    except (ValueError, TypeError):
        pass

    # Try all-float
    try:
        return [float(p) for p in parts]
    except (ValueError, TypeError):
        pass

    # Fallback: string array
    return parts


@register("csv")
def parse_csv(filepath: str | Path, **kwargs) -> list[Constant]:
    """Parse constants from a CSV file.

    Args:
        filepath: Path to .csv file.
        delimiter: Override delimiter (default: auto-detect).

    Returns:
        List of Constant objects.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"CSV file not found: {filepath}")

    text = filepath.read_text(encoding="utf-8")

    # Auto-detect delimiter
    delimiter = kwargs.get("delimiter")
    if delimiter is None:
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(text[:2048])
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ","

    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    rows = list(reader)

    if len(rows) < 2:
        return []

    # Header row — find columns
    headers = [h.strip().lower() for h in rows[0]]

    name_col = _find_col(headers, {"name", "constant", "parameter", "symbol"})
    value_col = _find_col(headers, {"value", "val", "data", "number"})
    unit_col = _find_col(headers, {"unit", "units", "uom"})
    desc_col = _find_col(headers, {"description", "desc", "comment", "note"})

    if name_col is None:
        name_col = 0
    if value_col is None:
        value_col = 1

    constants: list[Constant] = []
    for row in rows[1:]:
        if not row or not row[name_col].strip():
            continue

        name = row[name_col].strip()
        raw_value = row[value_col].strip() if value_col < len(row) else ""
        if not raw_value:
            continue

        value = _parse_value(raw_value)

        unit = row[unit_col].strip() if unit_col is not None and unit_col < len(row) else ""
        desc = row[desc_col].strip() if desc_col is not None and desc_col < len(row) else ""

        constants.append(Constant(name=name, value=value, unit=unit, description=desc))

    return constants


def _find_col(headers: list[str], aliases: set[str]) -> int | None:
    for i, h in enumerate(headers):
        if h in aliases:
            return i
    return None
