# Contributing to consync

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/naveenkumarbaskaran/consync.git
cd consync
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
```

All 77+ tests should pass. Tests cover precision, parsers, renderers, sync engine, and CLI.

## Code Style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
ruff check .
ruff format .
```

## Making Changes

1. Fork the repo and create a feature branch from `main`
2. Make your changes with clear, descriptive commits
3. Add or update tests for any new functionality
4. Ensure all tests pass and linting is clean
5. Open a pull request against `main`

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: add TOML renderer for constants output`
- `fix: handle hex values in C header parser`
- `test: add round-trip precision tests for verilog`
- `docs: update CLI reference for --from flag`

## Architecture Overview

```
Source (xlsx/csv/json/toml) ←→ [consync engine] ←→ Target (C/Python/Rust/Verilog/VHDL)
```

### Key Modules

- `consync/parsers/` — Read constants from various file formats
- `consync/renderers/` — Write constants to target languages
- `consync/sync.py` — Core sync engine (direction detection, state management)
- `consync/precision.py` — IEEE 754 precision formatting
- `consync/cli.py` — Click-based CLI entry point
- `consync/watcher.py` — File watcher for continuous sync
- `consync/state.py` — Hash-based change detection

## Adding a New Parser

1. Create `consync/parsers/your_format.py`
2. Implement a function that returns `list[Constant]`
3. Decorate with `@register("format_name")`
4. Import in `consync/parsers/__init__.py`
5. Add tests in `tests/test_parsers.py`

## Adding a New Renderer

1. Create `consync/renderers/your_format.py`
2. Implement a function that writes constants to a file
3. Decorate with `@register("format_name")`
4. Import in `consync/renderers/__init__.py`
5. Add tests in `tests/test_renderers.py`

## Reporting Issues

- Use GitHub Issues with a clear title and reproduction steps
- Include your Python version, OS, and error output
- For sync issues, include your `.consync.yaml` (redact any sensitive paths)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
