"""TOML parser — reads constants from a TOML file.

Supports two formats:

Format A (flat):
    [constants]
    R_SENSE = 1.9999999999910001
    R_PULLUP = 4706

Format B (tables with metadata):
    [constants.R_SENSE]
    value = 1.999
    unit = "Ohm"
    description = "Current sense resistor"
"""

from __future__ import annotations

import sys
from pathlib import Path

from consync.models import Constant
from consync.parsers import register


def _load_toml(filepath: Path) -> dict:
    """Load TOML file using tomllib (3.11+) or tomli."""
    text = filepath.read_text(encoding="utf-8")
    if sys.version_info >= (3, 11):
        import tomllib
        return tomllib.loads(text)
    else:
        try:
            import tomli
            return tomli.loads(text)
        except ImportError:
            raise ImportError(
                "TOML support requires Python 3.11+ or 'pip install tomli'. "
                "Install with: pip install consync[toml]"
            )


@register("toml")
def parse_toml(filepath: str | Path, **kwargs) -> list[Constant]:
    """Parse constants from a TOML file."""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"TOML file not found: {filepath}")

    data = _load_toml(filepath)

    # Look for a [constants] section, fallback to root
    section = data.get("constants", data)

    constants: list[Constant] = []
    for name, value in section.items():
        if isinstance(value, dict):
            # Format B: table with metadata
            val = value.get("value")
            if val is None:
                continue
            constants.append(Constant(
                name=name,
                value=val,
                unit=str(value.get("unit", "")),
                description=str(value.get("description", value.get("desc", ""))),
            ))
        elif isinstance(value, (int, float)):
            # Format A: flat key=value
            constants.append(Constant(name=name, value=value))
        elif isinstance(value, str):
            constants.append(Constant(name=name, value=value))

    return constants
