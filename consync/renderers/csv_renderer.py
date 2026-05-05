"""CSV renderer — writes constants to a CSV file."""

from __future__ import annotations

import csv
from pathlib import Path

from consync.models import Constant, MappingConfig
from consync.renderers import register


@register("csv")
def render_csv(
    constants: list[Constant],
    filepath: str | Path,
    *,
    config: MappingConfig | None = None,
    **kwargs,
) -> None:
    """Render constants as a CSV file with headers Name, Value, Unit, Description."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    delimiter = ","
    if filepath.suffix.lower() == ".tsv":
        delimiter = "\t"

    with filepath.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(["Name", "Value", "Unit", "Description"])
        for c in constants:
            # Format value: arrays use pipe separator, floats get precision
            if isinstance(c.value, list):
                if c.value and isinstance(c.value[0], float):
                    from consync.precision import format_float
                    precision = config.precision if config else 17
                    val_str = "|".join(format_float(v, precision) for v in c.value)
                else:
                    val_str = "|".join(str(v) for v in c.value)
            elif isinstance(c.value, float):
                from consync.precision import format_float
                precision = config.precision if config else 17
                val_str = format_float(c.value, precision)
            else:
                val_str = str(c.value)
            writer.writerow([c.name, val_str, c.unit or "", c.description or ""])
