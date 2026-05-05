"""Core data models for consync."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SyncDirection(Enum):
    """Which direction to sync constants."""

    SOURCE_TO_TARGET = "source_to_target"
    TARGET_TO_SOURCE = "target_to_source"
    BOTH = "both"


class ConstantType(Enum):
    """Supported constant value types."""

    FLOAT = "float"
    INT = "int"
    STRING = "string"


@dataclass
class Constant:
    """A single named constant with value and metadata.

    This is the universal data model — every parser produces these,
    every renderer consumes them.
    """

    name: str
    value: float | int | str
    unit: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> ConstantType:
        if isinstance(self.value, int):
            return ConstantType.INT
        if isinstance(self.value, float):
            return ConstantType.FLOAT
        return ConstantType.STRING

    @property
    def is_numeric(self) -> bool:
        return isinstance(self.value, (int, float))


@dataclass
class MappingConfig:
    """Configuration for a single source ↔ target mapping."""

    source: str
    target: str
    source_format: str = ""  # auto-detect from extension if empty
    target_format: str = ""  # auto-detect from extension if empty
    direction: SyncDirection = SyncDirection.SOURCE_TO_TARGET
    precision: int = 17  # significant digits for floats
    header_guard: str = ""  # C header guard name
    namespace: str = ""  # for Rust/C++ namespacing
    module_name: str = ""  # for Verilog/VHDL module scoping
    prefix: str = ""  # prefix added to all constant names
    uppercase_names: bool = True  # force UPPER_CASE names in output


@dataclass
class ConsyncConfig:
    """Root configuration loaded from .consync.yaml."""

    mappings: list[MappingConfig] = field(default_factory=list)
    state_file: str = ".consync.state.json"
    watch_debounce: float = 2.0  # seconds
    on_conflict: str = "source_wins"  # source_wins | target_wins | fail
