"""CSV parser — reads constants from comma/tab-separated files.

Expected format:
  Row 1: Header (Name, Value, Unit, Description)
  Row 2+: Data

Auto-detects delimiter (comma, tab, semicolon).
"""

from __future__ import annotations

import csv
from pathlib import Path

from consync.models import Constant
from consync.parsers import register
from consync.precision import parse_number


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

        try:
            value = parse_number(raw_value)
        except (ValueError, IndexError):
            value = raw_value

        unit = row[unit_col].strip() if unit_col is not None and unit_col < len(row) else ""
        desc = row[desc_col].strip() if desc_col is not None and desc_col < len(row) else ""

        constants.append(Constant(name=name, value=value, unit=unit, description=desc))

    return constants


def _find_col(headers: list[str], aliases: set[str]) -> int | None:
    for i, h in enumerate(headers):
        if h in aliases:
            return i
    return None
