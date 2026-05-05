"""Configuration loader for .consync.yaml files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from consync.models import ConsyncConfig, MappingConfig, SyncDirection

DEFAULT_CONFIG_NAME = ".consync.yaml"

# Format auto-detection from file extensions
EXTENSION_TO_FORMAT: dict[str, str] = {
    ".xlsx": "xlsx",
    ".xls": "xlsx",
    ".csv": "csv",
    ".json": "json",
    ".toml": "toml",
    ".h": "c_header",
    ".hpp": "c_header",
    ".hh": "c_header",
    ".c": "c_header",
    ".cs": "csharp",
    ".py": "python",
    ".rs": "rust",
    ".v": "verilog",
    ".sv": "verilog",
    ".vhd": "vhdl",
    ".vhdl": "vhdl",
}


def find_config(start_dir: Path | None = None) -> Path | None:
    """Walk up from start_dir looking for .consync.yaml.

    Similar to how .gitignore or pyproject.toml are found.
    """
    if start_dir is None:
        start_dir = Path.cwd()
    start_dir = start_dir.resolve()

    for directory in [start_dir, *start_dir.parents]:
        candidate = directory / DEFAULT_CONFIG_NAME
        if candidate.exists():
            return candidate
    return None


def detect_format(filepath: str) -> str:
    """Auto-detect format from file extension."""
    ext = Path(filepath).suffix.lower()
    fmt = EXTENSION_TO_FORMAT.get(ext, "")
    if not fmt:
        raise ValueError(
            f"Cannot auto-detect format for '{filepath}'. "
            f"Supported extensions: {', '.join(sorted(EXTENSION_TO_FORMAT.keys()))}. "
            f"Specify format explicitly in .consync.yaml."
        )
    return fmt


def _parse_direction(raw: str) -> SyncDirection:
    """Parse direction string from YAML config."""
    mapping = {
        "source_to_target": SyncDirection.SOURCE_TO_TARGET,
        "target_to_source": SyncDirection.TARGET_TO_SOURCE,
        "both": SyncDirection.BOTH,
        "s2t": SyncDirection.SOURCE_TO_TARGET,
        "t2s": SyncDirection.TARGET_TO_SOURCE,
        "bidirectional": SyncDirection.BOTH,
    }
    normalized = raw.lower().strip().replace("-", "_").replace(" ", "_")
    if normalized not in mapping:
        raise ValueError(
            f"Invalid direction '{raw}'. "
            f"Use: source_to_target, target_to_source, or both."
        )
    return mapping[normalized]


def _parse_mapping(raw: dict[str, Any], config_dir: Path) -> MappingConfig:
    """Parse a single mapping entry from YAML."""
    source = raw.get("source", "")
    target = raw.get("target", "")

    if not source:
        raise ValueError("Each mapping must have a 'source' field.")
    if not target:
        raise ValueError("Each mapping must have a 'target' field.")

    source_format = raw.get("source_format", "") or raw.get("format_source", "")
    target_format = raw.get("target_format", "") or raw.get("format_target", "") or raw.get("format", "")

    # Auto-detect formats if not specified
    if not source_format:
        source_format = detect_format(source)
    if not target_format:
        target_format = detect_format(target)

    direction = _parse_direction(raw.get("direction", "source_to_target"))

    return MappingConfig(
        source=source,
        target=target,
        source_format=source_format,
        target_format=target_format,
        direction=direction,
        precision=int(raw.get("precision", 17)),
        header_guard=raw.get("header_guard", ""),
        namespace=raw.get("namespace", ""),
        module_name=raw.get("module_name", ""),
        prefix=raw.get("prefix", ""),
        uppercase_names=raw.get("uppercase_names", True),
        output_style=raw.get("output_style", "const"),
        static_const=raw.get("static_const", False),
        typed_ints=raw.get("typed_ints", True),
        validators=raw.get("validators", {}),
    )


def load_config(config_path: Path | str | None = None) -> ConsyncConfig:
    """Load and validate a .consync.yaml configuration.

    Args:
        config_path: Explicit path to config file. If None, searches
                     upward from CWD.

    Returns:
        Parsed ConsyncConfig.

    Raises:
        FileNotFoundError: If no config file found.
        ValueError: If config is invalid.
    """
    if config_path is None:
        found = find_config()
        if found is None:
            raise FileNotFoundError(
                f"No {DEFAULT_CONFIG_NAME} found. Run 'consync init' to create one."
            )
        config_path = found
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    config_dir = config_path.parent

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError(f"Invalid config: expected a YAML mapping, got {type(raw).__name__}")

    raw_mappings = raw.get("mappings", [])
    if not raw_mappings:
        raise ValueError("Config must have at least one entry in 'mappings'.")

    mappings = [_parse_mapping(m, config_dir) for m in raw_mappings]

    return ConsyncConfig(
        mappings=mappings,
        state_file=raw.get("state_file", ".consync.state.json"),
        watch_debounce=float(raw.get("watch_debounce", 2.0)),
        on_conflict=raw.get("on_conflict", "source_wins"),
    )


def generate_default_config() -> str:
    """Generate a default .consync.yaml template for `consync init`."""
    return """\
# consync configuration — https://github.com/naveenkumarbaskaran/consync
# Sync constants between spreadsheets and source code with full decimal precision.

mappings:
  - source: constants.xlsx          # Where constants are defined (spreadsheet)
    target: include/constants.h     # Generated code file
    direction: both                 # source_to_target | target_to_source | both
    precision: 17                   # Significant digits (17 = full IEEE 754 double)
    header_guard: HW_CONSTANTS_H   # C header include guard

    # Optional:
    # prefix: ""                    # Prefix all constant names (e.g., "HW_")
    # uppercase_names: true         # Force UPPER_CASE names in output

  # Add more mappings as needed:
  # - source: parameters.xlsx
  #   target: src/params.v
  #   direction: source_to_target
  #   precision: 12
  #   module_name: design_params

# Global settings:
# state_file: .consync.state.json   # Track sync state (gitignore this)
# watch_debounce: 2.0               # Seconds to wait before re-syncing
# on_conflict: source_wins          # source_wins | target_wins | fail
"""
