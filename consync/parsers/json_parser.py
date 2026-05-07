"""JSON parser — reads constants from a JSON file.

Supports two formats:

Format A (flat object):
    {
        "R_SENSE": 1.9999999999910001,
        "R_PULLUP": 4706
    }

Format B (array with metadata):
    [
        {"name": "R_SENSE", "value": 1.999, "unit": "Ohm", "description": "..."},
        ...
    ]

Format C (nested object):
    {
        "R_SENSE": {"value": 1.999, "unit": "Ohm", "description": "..."},
        ...
    }
"""

from __future__ import annotations

import json
from pathlib import Path

from consync.models import Constant
from consync.parsers import register
from consync.precision import parse_number


@register("json")
def parse_json(filepath: str | Path, **kwargs) -> list[Constant]:
    """Parse constants from a JSON file.

    Auto-detects format (flat, array, or nested object).
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"JSON file not found: {filepath}")

    data = json.loads(filepath.read_text(encoding="utf-8"))

    # Format B: array of objects
    if isinstance(data, list):
        return _parse_array(data)

    # Format A or C: object
    if isinstance(data, dict):
        # Format D: consync renderer output {"_meta": {...}, "constants": [...]}
        if "constants" in data and isinstance(data["constants"], list):
            return _parse_array(data["constants"])

        # Check first value to distinguish A vs C
        first_val = next(iter(data.values()), None) if data else None
        if isinstance(first_val, dict):
            return _parse_nested(data)
        return _parse_flat(data)

    raise ValueError(f"Unexpected JSON structure: expected object or array, got {type(data).__name__}")


def _parse_flat(data: dict) -> list[Constant]:
    """Format A: {"NAME": value, ...} — value can be scalar or array."""
    constants = []
    for name, value in data.items():
        if isinstance(value, list):
            # Array constant — typed list of ints, floats, or strings
            constants.append(Constant(name=name, value=_coerce_array(value)))
        elif isinstance(value, (int, float)):
            constants.append(Constant(name=name, value=value))
        elif isinstance(value, str):
            try:
                constants.append(Constant(name=name, value=parse_number(value)))
            except ValueError:
                constants.append(Constant(name=name, value=value))
    return constants


def _parse_array(data: list) -> list[Constant]:
    """Format B: [{"name": ..., "value": ..., ...}, ...]"""
    constants = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "")
        value = item.get("value")
        if not name or value is None:
            continue
        # Support array values in Format B
        if isinstance(value, list):
            value = _coerce_array(value)
        constants.append(Constant(
            name=name,
            value=value,
            unit=str(item.get("unit", "")),
            description=str(item.get("description", item.get("desc", ""))),
        ))
    return constants


def _parse_nested(data: dict) -> list[Constant]:
    """Format C: {"NAME": {"value": ..., "unit": ..., ...}, ...}"""
    constants = []
    for name, props in data.items():
        if not isinstance(props, dict):
            continue
        value = props.get("value")
        if value is None:
            continue
        # Support array values in Format C
        if isinstance(value, list):
            value = _coerce_array(value)
        constants.append(Constant(
            name=name,
            value=value,
            unit=str(props.get("unit", "")),
            description=str(props.get("description", props.get("desc", ""))),
        ))
    return constants


def _coerce_array(arr: list) -> list[int] | list[float] | list[str]:
    """Coerce a JSON array into a typed Python list.

    Priority: int → float → str.
    """
    if not arr:
        return []

    # Check if all ints
    if all(isinstance(x, int) for x in arr):
        return arr

    # Check if all numeric (mix of int/float → float)
    if all(isinstance(x, (int, float)) for x in arr):
        return [float(x) for x in arr]

    # Fallback to strings
    return [str(x) for x in arr]
