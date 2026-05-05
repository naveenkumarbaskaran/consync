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
    ARRAY_INT = "array_int"
    ARRAY_FLOAT = "array_float"
    ARRAY_STRING = "array_string"


@dataclass
class Constant:
    """A single named constant with value and metadata.

    This is the universal data model — every parser produces these,
    every renderer consumes them.

    Values can be scalars (int, float, str) or typed arrays (list[int],
    list[float], list[str]) for array constants like lookup tables.
    """

    name: str
    value: float | int | str | list[int] | list[float] | list[str]
    unit: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> ConstantType:
        if isinstance(self.value, list):
            if not self.value:
                return ConstantType.ARRAY_INT  # empty defaults to int array
            first = self.value[0]
            if isinstance(first, int):
                return ConstantType.ARRAY_INT
            elif isinstance(first, float):
                return ConstantType.ARRAY_FLOAT
            return ConstantType.ARRAY_STRING
        if isinstance(self.value, int):
            return ConstantType.INT
        if isinstance(self.value, float):
            return ConstantType.FLOAT
        return ConstantType.STRING

    @property
    def is_numeric(self) -> bool:
        if isinstance(self.value, list):
            return self.type in (ConstantType.ARRAY_INT, ConstantType.ARRAY_FLOAT)
        return isinstance(self.value, (int, float))

    @property
    def is_array(self) -> bool:
        return isinstance(self.value, list)


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
    # C/C++ specific options
    output_style: str = "const"  # "const" | "define" — #define vs const declaration
    static_const: bool = False  # emit "static const" to avoid linker duplicates
    typed_ints: bool = True  # use uint32_t/int32_t instead of plain int/double for integers


@dataclass
class ConsyncConfig:
    """Root configuration loaded from .consync.yaml."""

    mappings: list[MappingConfig] = field(default_factory=list)
    state_file: str = ".consync.state.json"
    watch_debounce: float = 2.0  # seconds
    on_conflict: str = "source_wins"  # source_wins | target_wins | fail
