"""JSON renderer — writes constants to a structured JSON file.

Output format:
    {
        "_meta": {
            "generator": "consync",
            "source": "constants.xlsx",
            "synced": "2026-05-05T14:30:00"
        },
        "constants": [
            {
                "name": "R_SENSE",
                "value": 1.9999999999910001,
                "unit": "Ohm",
                "description": "Current sense resistor"
            },
            ...
        ]
    }
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from consync.models import Constant, MappingConfig
from consync.renderers import register


@register("json")
def render_json(
    constants: list[Constant],
    filepath: str | Path,
    *,
    config: MappingConfig | None = None,
    **kwargs,
) -> None:
    """Render constants as a JSON file with metadata."""
    filepath = Path(filepath)
    source_name = config.source if config else kwargs.get("source", "unknown")
    prefix = config.prefix if config else kwargs.get("prefix", "")

    output = {
        "_meta": {
            "generator": "consync",
            "source": source_name,
            "synced": datetime.now().isoformat(timespec="seconds"),
        },
        "constants": [],
    }

    for c in constants:
        name = prefix + c.name
        if config and config.uppercase_names:
            name = name.upper()

        entry: dict = {"name": name, "value": c.value}
        if c.unit:
            entry["unit"] = c.unit
        if c.description:
            entry["description"] = c.description

        output["constants"].append(entry)

    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
