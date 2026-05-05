"""Renderer registry — maps format names to renderer functions."""

from __future__ import annotations

from typing import Callable

from consync.models import Constant as Constant  # re-export for type hints

# Type for renderer functions: (constants, filepath, **kwargs) -> None
RendererFunc = Callable[..., None]

_REGISTRY: dict[str, RendererFunc] = {}


def register(name: str):
    """Decorator to register a renderer function."""
    def decorator(func: RendererFunc) -> RendererFunc:
        _REGISTRY[name] = func
        return func
    return decorator


def get_renderer(format_name: str) -> RendererFunc:
    """Get a renderer by format name."""
    if format_name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"Unknown renderer format '{format_name}'. Available: {available}"
        )
    return _REGISTRY[format_name]


def list_renderers() -> list[str]:
    """List all registered renderer format names."""
    return sorted(_REGISTRY.keys())


# Import all renderer modules to trigger registration
from consync.renderers import (  # noqa: E402, F401
    c_header,
    csharp,
    csv_renderer,
    python_const,
    rust_const,
    verilog,
    vhdl,
    json_renderer,
)
