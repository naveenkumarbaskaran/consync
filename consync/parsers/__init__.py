"""Parser registry — maps format names to parser functions."""

from __future__ import annotations

from typing import Callable

from consync.models import Constant

# Type for parser functions: (filepath, **kwargs) -> list[Constant]
ParserFunc = Callable[..., list[Constant]]

_REGISTRY: dict[str, ParserFunc] = {}


def register(name: str):
    """Decorator to register a parser function."""
    def decorator(func: ParserFunc) -> ParserFunc:
        _REGISTRY[name] = func
        return func
    return decorator


def get_parser(format_name: str) -> ParserFunc:
    """Get a parser by format name."""
    if format_name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"Unknown parser format '{format_name}'. Available: {available}"
        )
    return _REGISTRY[format_name]


def list_parsers() -> list[str]:
    """List all registered parser format names."""
    return sorted(_REGISTRY.keys())


# Import all parser modules to trigger registration
from consync.parsers import xlsx, csv_parser, json_parser, toml_parser, c_header  # noqa: E402, F401
