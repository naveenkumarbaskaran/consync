"""Excel (.xlsx) parser — reads constants from a spreadsheet.

Expected format:
  Row 1: Header row (Name, Value, Unit, Description)
  Row 2+: Data rows

Column mapping is flexible — auto-detects by header names.
"""

from __future__ import annotations

from pathlib import Path

from consync.models import Constant
from consync.parsers import register


# Column header aliases (case-insensitive matching)
NAME_ALIASES = {"name", "constant", "parameter", "variable", "symbol", "id"}
VALUE_ALIASES = {"value", "val", "data", "number", "amount"}
UNIT_ALIASES = {"unit", "units", "uom", "dimension"}
DESC_ALIASES = {"description", "desc", "comment", "note", "notes", "info"}


def _find_column(headers: list[str], aliases: set[str]) -> int | None:
    """Find column index matching any alias (case-insensitive)."""
    for i, h in enumerate(headers):
        if h and h.strip().lower() in aliases:
            return i
    return None


@register("xlsx")
def parse_xlsx(filepath: str | Path, **kwargs) -> list[Constant]:
    """Parse constants from an Excel file.

    Args:
        filepath: Path to .xlsx file.
        sheet: Sheet name or index (default: active sheet).

    Returns:
        List of Constant objects.
    """
    import openpyxl

    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Excel file not found: {filepath}")

    wb = openpyxl.load_workbook(filepath, data_only=True)

    sheet = kwargs.get("sheet")
    if sheet is not None:
        if isinstance(sheet, int):
            ws = wb.worksheets[sheet]
        else:
            ws = wb[sheet]
    else:
        ws = wb.active

    # Read header row
    header_row = [str(cell.value or "").strip() for cell in ws[1]]

    # Auto-detect columns
    name_col = _find_column(header_row, NAME_ALIASES)
    value_col = _find_column(header_row, VALUE_ALIASES)
    unit_col = _find_column(header_row, UNIT_ALIASES)
    desc_col = _find_column(header_row, DESC_ALIASES)

    # Fallback to positional: A=Name, B=Value, C=Unit, D=Description
    if name_col is None:
        name_col = 0
    if value_col is None:
        value_col = 1
    if unit_col is None:
        unit_col = 2 if len(header_row) > 2 else None
    if desc_col is None:
        desc_col = 3 if len(header_row) > 3 else None

    constants: list[Constant] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[name_col] is None:
            continue

        name = str(row[name_col]).strip()
        if not name:
            continue

        raw_value = row[value_col] if value_col < len(row) else None
        if raw_value is None:
            continue

        # Preserve numeric types
        if isinstance(raw_value, (int, float)):
            value = raw_value
        else:
            # Try to parse as number
            try:
                value = int(str(raw_value))
            except ValueError:
                try:
                    value = float(str(raw_value))
                except ValueError:
                    value = str(raw_value)

        unit = ""
        if unit_col is not None and unit_col < len(row) and row[unit_col]:
            unit = str(row[unit_col]).strip()

        description = ""
        if desc_col is not None and desc_col < len(row) and row[desc_col]:
            description = str(row[desc_col]).strip()

        constants.append(Constant(name=name, value=value, unit=unit, description=description))

    return constants
